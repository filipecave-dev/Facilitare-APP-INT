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
