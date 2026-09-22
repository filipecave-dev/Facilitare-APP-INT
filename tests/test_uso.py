"""Testes de contabilidade de uso/custo de IA e do teto diário."""

from __future__ import annotations

import pytest

from informativo.db import Database, init_db
from informativo.settings_repo import SettingsRepository
from informativo.uso import (
    CFG_LIMITE_DIA, CFG_PRECO_IN, CFG_PRECO_OUT, Precos, UsoRepository, excede_limite,
)


@pytest.fixture()
def db(tmp_path):
    with Database(f"sqlite:///{tmp_path}/u.db") as conexao:
        init_db(conexao)
        yield conexao


def test_precos_padrao_e_custo(db):
    precos = Precos(SettingsRepository(db))
    # padrões pensados para o Gemini Flash-Lite
    assert precos.preco_in > 0 and precos.preco_out > 0
    # 1M in + 1M out = preco_in + preco_out
    assert round(precos.custo(1_000_000, 1_000_000), 6) == \
        round(precos.preco_in + precos.preco_out, 6)


def test_registrar_e_total_do_dia(db):
    precos = Precos(SettingsRepository(db))
    uso = UsoRepository(db)
    c1 = precos.custo(1000, 500)
    uso.registrar("captura", {"in": 1000, "out": 500}, c1, provedor="Gemini")
    uso.registrar("parafrase", {"in": 300, "out": 200}, precos.custo(300, 200))
    tot = uso.total_do_dia()
    assert tot["chamadas"] == 2
    assert tot["tokens_in"] == 1300 and tot["tokens_out"] == 700
    assert tot["custo"] > 0


def test_limite_diario_bloqueia(db):
    settings = SettingsRepository(db)
    # preços altos + limite baixo para estourar rápido
    settings.set(CFG_PRECO_IN, "10")   # US$10 / 1M
    settings.set(CFG_PRECO_OUT, "30")
    settings.set(CFG_LIMITE_DIA, "0.01")
    precos = Precos(settings)
    uso = UsoRepository(db)
    assert excede_limite(uso, precos) is False
    # uma chamada de 1000/500 tokens custa 10*0.001 + 30*0.0005 = 0.025 > 0.01
    uso.registrar("captura", {"in": 1000, "out": 500}, precos.custo(1000, 500))
    assert excede_limite(uso, precos) is True


def test_sem_limite_nunca_bloqueia(db):
    settings = SettingsRepository(db)
    settings.set(CFG_LIMITE_DIA, "0")  # 0 = sem limite
    precos = Precos(settings)
    uso = UsoRepository(db)
    uso.registrar("captura", {"in": 10_000_000, "out": 10_000_000},
                  precos.custo(10_000_000, 10_000_000))
    assert excede_limite(uso, precos) is False


def test_curva_abc_por_fonte(db):
    precos = Precos(SettingsRepository(db))
    uso = UsoRepository(db)
    # Fonte grande domina o consumo (classe A); duas pequenas (B/C).
    uso.registrar("captura", {"in": 90000, "out": 10000}, precos.custo(90000, 10000),
                  fonte_id=1, fonte_nome="Reuters")
    uso.registrar("captura", {"in": 6000, "out": 2000}, precos.custo(6000, 2000),
                  fonte_id=2, fonte_nome="G1")
    uso.registrar("parafrase", {"in": 1500, "out": 500}, precos.custo(1500, 500),
                  fonte_id=3, fonte_nome="CNN")
    abc = uso.curva_abc()
    itens = abc["itens"]
    assert [i["fonte_nome"] for i in itens] == ["Reuters", "G1", "CNN"]  # ordenado desc
    assert itens[0]["classe"] == "A"  # Reuters concentra o consumo
    # acumulado termina em ~100%
    assert round(itens[-1]["pct_acumulado"], 3) == 1.0
    # totais coerentes
    assert abc["totais"]["tokens"] == 100000 + 8000 + 2000
    assert abc["totais"]["fontes"] == 3
    # classes somam todas as fontes
    somaf = sum(abc["classes"][c]["fontes"] for c in ("A", "B", "C"))
    assert somaf == 3


def test_resumo_do_dia_tem_resta(db):
    settings = SettingsRepository(db)
    settings.set(CFG_LIMITE_DIA, "1.00")
    settings.set(CFG_PRECO_IN, "0.10")
    settings.set(CFG_PRECO_OUT, "0.40")
    precos = Precos(settings)
    uso = UsoRepository(db)
    uso.registrar("captura", {"in": 1000, "out": 500}, precos.custo(1000, 500))
    r = uso.resumo_do_dia(precos)
    assert r["limite"] == 1.0
    assert r["resta"] == pytest.approx(1.0 - r["custo"])
    assert r["atingido"] is False
