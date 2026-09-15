"""Testes dos provedores de IA (conexões) e do cliente."""

from __future__ import annotations

import io
import json

import pytest

from informativo.db import Database, init_db
from informativo.empresas import EmpresaRepository
from informativo.provedores import ClienteIA, IAError, ProvedorRepository


@pytest.fixture()
def db(tmp_path):
    with Database(f"sqlite:///{tmp_path}/p.db") as conexao:
        init_db(conexao)
        yield conexao


def test_endpoints_por_formato():
    assert ClienteIA("openai", "http://x:20128", "m")._endpoint_openai() == \
        "http://x:20128/v1/chat/completions"
    # Gemini (OpenAI-compatible) termina em /v1beta/openai -> só /chat/completions
    assert ClienteIA(
        "openai", "https://generativelanguage.googleapis.com/v1beta/openai", "m"
    )._endpoint_openai() == \
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    # base terminando em /v1
    assert ClienteIA("openai", "https://api.deepseek.com/v1", "m")._endpoint_openai() == \
        "https://api.deepseek.com/v1/chat/completions"
    # URL completa colada pelo usuário
    assert ClienteIA("openai", "http://x/v1/chat/completions", "m")._endpoint_openai() == \
        "http://x/v1/chat/completions"
    assert ClienteIA("anthropic", "https://api.anthropic.com", "m")._endpoint_anthropic() == \
        "https://api.anthropic.com/v1/messages"


def test_criar_provedor_global_e_por_empresa(db):
    er = EmpresaRepository(db)
    empresa = er.criar("Acme")
    pr = ProvedorRepository(db)
    g = pr.criar("OmniRoute", "openai", "http://x:20128", "deepseek-chat", api_key="k")
    e = pr.criar("Claude Acme", "anthropic", "https://api.anthropic.com",
                 "claude-haiku-4-5", api_key="sk", empresa_id=empresa.id)
    assert g.empresa_id is None
    assert e.empresa_id == empresa.id
    assert len(pr.listar()) == 2
    assert len(pr.listar(empresa_id=empresa.id)) == 1


def test_provedor_validacoes(db):
    pr = ProvedorRepository(db)
    with pytest.raises(ValueError):
        pr.criar("", "openai", "http://x", "m")
    with pytest.raises(ValueError):
        pr.criar("X", "formato-invalido", "http://x", "m")
    with pytest.raises(ValueError):
        pr.criar("X", "openai", "", "m")


def test_atualizar_preserva_chave_quando_ausente(db):
    pr = ProvedorRepository(db)
    p = pr.criar("Gemini", "openai", "http://x/v1beta/openai", "gemini-flash-latest",
                 api_key="chave-antiga")
    # Atualiza sem mexer na chave.
    pr.atualizar(p.id, modelo="gemini-2.0-flash")
    atual = pr.get(p.id)
    assert atual.modelo == "gemini-2.0-flash"
    assert atual.api_key == "chave-antiga"
    # Agora troca a chave.
    pr.atualizar(p.id, api_key="chave-nova")
    assert pr.get(p.id).api_key == "chave-nova"


def test_atualizar_formato_invalido(db):
    pr = ProvedorRepository(db)
    p = pr.criar("X", "openai", "http://x", "m")
    with pytest.raises(ValueError):
        pr.atualizar(p.id, formato="zzz")


def test_alternar_e_remover(db):
    pr = ProvedorRepository(db)
    p = pr.criar("X", "openai", "http://x", "m")
    assert pr.get(p.id).ativo is True
    pr.alternar_ativo(p.id)
    assert pr.get(p.id).ativo is False
    pr.remover(p.id)
    assert pr.get(p.id) is None


def test_cliente_openai_parseia(monkeypatch):
    payload = {"choices": [{"message": {"content": "  oi  "}}]}

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=None):
        assert req.get_header("Authorization") == "Bearer k"
        return _R(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert ClienteIA("openai", "http://x", "m", "k").chat("oi") == "oi"


def test_cliente_anthropic_parseia(monkeypatch):
    payload = {"content": [{"type": "text", "text": "resposta claude"}]}

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=None):
        # headers da Anthropic
        assert req.get_header("X-api-key") == "sk"
        assert req.get_header("Anthropic-version") is not None
        corpo = json.loads(req.data.decode())
        assert corpo["max_tokens"] > 0
        return _R(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    cli = ClienteIA("anthropic", "https://api.anthropic.com", "claude-haiku-4-5", "sk")
    assert cli.chat("oi", system="s") == "resposta claude"


def test_cliente_sem_config():
    with pytest.raises(IAError):
        ClienteIA("openai", "", "m").chat("oi")
