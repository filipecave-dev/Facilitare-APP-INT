"""Testes do cliente Omniroute e do repositório de captações."""

from __future__ import annotations

import io
import json

import pytest

from informativo.db import Database, init_db
from informativo.fontes import FonteRepository
from informativo.omniroute import (
    CaptacaoRepository,
    OmnirouteClient,
    OmnirouteError,
    prompt_parafrase,
    prompt_para_fonte,
)


@pytest.fixture()
def db(tmp_path):
    with Database(f"sqlite:///{tmp_path}/o.db") as conexao:
        init_db(conexao)
        yield conexao


def test_endpoint_openai_compat():
    assert OmnirouteClient("http://x:20128").  _endpoint() == "http://x:20128/v1/chat/completions"
    assert OmnirouteClient("http://x/v1")._endpoint() == "http://x/v1/chat/completions"
    assert (
        OmnirouteClient("http://x/v1/chat/completions")._endpoint()
        == "http://x/v1/chat/completions"
    )
    # barra final é normalizada
    assert OmnirouteClient("http://x:20128/")._endpoint() == "http://x:20128/v1/chat/completions"


def test_configurado():
    assert OmnirouteClient("http://x", modelo="m").configurado()
    assert not OmnirouteClient("", modelo="m").configurado()
    assert not OmnirouteClient("http://x", modelo="").configurado()


def test_chat_parseia_resposta(monkeypatch):
    payload = {"choices": [{"message": {"content": "  Olá  "}}]}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        # confere que o corpo tem o modelo e as mensagens
        corpo = json.loads(req.data.decode())
        assert corpo["model"] == "meu-modelo"
        assert corpo["messages"][-1]["role"] == "user"
        return _Resp(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cli = OmnirouteClient("http://x", api_key="k", modelo="meu-modelo")
    assert cli.chat("oi") == "Olá"


def test_chat_sem_config_levanta():
    with pytest.raises(OmnirouteError):
        OmnirouteClient("", modelo="m").chat("oi")
    with pytest.raises(OmnirouteError):
        OmnirouteClient("http://x", modelo="").chat("oi")


def test_prompt_para_fonte_usa_dados(db):
    repo = FonteRepository(db)
    f = repo.criar("Reuters", "reuters.com", categoria="Geral", regiao="Internacional")
    system, prompt = prompt_para_fonte(f)
    assert "analista" in system.lower()
    assert "Reuters" in prompt and "Internacional" in prompt


def test_captacao_repository(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    assert cap.count() == 0
    cap.registrar(f, "resumo de teste")
    assert cap.count() == 1
    recentes = cap.listar_recentes()
    assert recentes[0]["fonte_nome"] == "Reuters"
    assert recentes[0]["conteudo"] == "resumo de teste"


def test_reclassificar_e_parafrasear(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    cap.registrar(f, "resumo original")
    cid = cap.listar_recentes()[0]["id"]
    # reclassificar em uma frente (mesmo após aprovado)
    cap.definir_status(cid, "aprovada")
    cap.definir_frente(cid, "Alerta")
    assert cap.get(cid)["frente"] == "Alerta"
    with pytest.raises(ValueError):
        cap.definir_frente(cid, "Inexistente")
    # limpar frente com vazio
    cap.definir_frente(cid, "")
    assert cap.get(cid)["frente"] is None
    # guardar paráfrase
    cap.definir_parafrase(cid, "texto reescrito")
    assert cap.get(cid)["parafrase"] == "texto reescrito"


def test_limpar_captacoes_por_status(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    cap.registrar(f, "a")
    cap.registrar(f, "b")
    ids = [c["id"] for c in cap.listar_recentes()]
    cap.definir_status(ids[0], "aprovada")
    # limpa só as pendentes
    assert cap.limpar(status="pendente") == 1
    assert cap.count() == 1
    # limpa tudo
    assert cap.limpar() == 1
    assert cap.count() == 0


def test_prompt_parafrase_tem_frente_e_conteudo(db):
    cap = {
        "fonte_nome": "Reuters", "regiao": "Brasil",
        "frente": "Notícias de Mercado", "conteudo": "texto base",
    }
    system, prompt = prompt_parafrase(cap, nome_solucao="Boletim ACME")
    assert "paráfrase" in system.lower() or "reescreva" in system.lower()
    assert "Notícias de Mercado" in system
    assert "texto base" in prompt and "Boletim ACME" in prompt
