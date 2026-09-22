"""Testes do regressivo do plano gratuito do banco (Render)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from informativo.db import Database, init_db
from informativo.plano import (
    CFG_DB_DIAS, CFG_DB_INICIO, contagem_regressiva, garantir_inicio, hoje,
)
from informativo.settings_repo import SettingsRepository


@pytest.fixture()
def settings(tmp_path):
    with Database(f"sqlite:///{tmp_path}/p.db") as db:
        init_db(db)
        yield SettingsRepository(db)


def test_garantir_inicio_define_hoje(settings):
    assert settings.get(CFG_DB_INICIO) is None
    inicio = garantir_inicio(settings)
    assert inicio == hoje().isoformat()
    # idempotente: não sobrescreve
    settings.set(CFG_DB_INICIO, "2026-01-01")
    assert garantir_inicio(settings) == "2026-01-01"


def test_contagem_regressiva_restantes(settings):
    inicio = hoje() - timedelta(days=10)
    settings.set(CFG_DB_INICIO, inicio.isoformat())
    settings.set(CFG_DB_DIAS, "30")
    c = contagem_regressiva(settings)
    assert c["dias_total"] == 30
    assert c["restantes"] == 20
    assert c["expirado"] is False
    assert c["expira"] == inicio + timedelta(days=30)
    assert c["pct"] == round(10 / 30 * 100)


def test_contagem_alerta_e_expirado(settings):
    settings.set(CFG_DB_DIAS, "30")
    # faltando 5 dias -> alerta
    settings.set(CFG_DB_INICIO, (hoje() - timedelta(days=25)).isoformat())
    assert contagem_regressiva(settings)["alerta"] is True
    # já venceu
    settings.set(CFG_DB_INICIO, (hoje() - timedelta(days=40)).isoformat())
    c = contagem_regressiva(settings)
    assert c["expirado"] is True and c["restantes"] < 0


def test_sem_inicio_retorna_none(settings):
    assert contagem_regressiva(settings) is None
