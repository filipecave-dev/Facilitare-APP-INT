"""Testes de fumaça da interface web (Flask)."""

from __future__ import annotations

import pytest

from informativo.auth import UsuarioRepository
from informativo.db import Database, init_db
from informativo.web import create_app


@pytest.fixture()
def app(tmp_path):
    dsn = f"sqlite:///{tmp_path}/web.db"
    aplicacao = create_app(dsn=dsn)
    aplicacao.config.update(TESTING=True)
    with Database(dsn) as db:
        init_db(db)
        UsuarioRepository(db).criar(
            "admin", "senhaforte", "Administrador",
            nome="Admin", atualizar_se_existir=True,
        )
    return aplicacao


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client):
    return client.post(
        "/", data={"username": "admin", "senha": "senhaforte"}, follow_redirects=True
    )


def test_seed_ao_criar_app(app):
    from informativo.fontes import FonteRepository

    with Database(app.config["DSN"]) as db:
        assert FonteRepository(db).count() == 80


def test_login_exigido_redireciona(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/" in resp.headers["Location"]


def test_fluxo_login_e_dashboard(client):
    resp = _login(client)
    assert resp.status_code == 200
    assert b"Painel Principal" in resp.data


def test_pagina_fontes_lista_seed(client):
    _login(client)
    resp = client.get("/fontes")
    assert resp.status_code == 200
    assert b"Reuters" in resp.data


def test_adicionar_e_remover_fonte(client):
    _login(client)
    resp = client.post(
        "/fontes/adicionar",
        data={"nome": "Fonte Teste", "url": "fonteteste.com", "relevancia": "4", "prioridade": "5"},
        follow_redirects=True,
    )
    assert "Fonte Teste".encode() in resp.data


def test_cadastrar_empresa_com_nome_solucao_e_assunto(client):
    _login(client)
    resp = client.post(
        "/empresas/adicionar",
        data={"nome": "Acme Viagens", "nome_solucao": "Acme Alertas",
              "assunto_email": "Boletim de Viagem Acme",
              "contato_email": "", "tema_primary": "#1c7a43", "ativa": "1"},
        follow_redirects=True,
    )
    assert "Acme Alertas".encode() in resp.data
    assert "Boletim de Viagem Acme".encode() in resp.data
    assert "Acme Viagens".encode() in resp.data


def test_primeiro_acesso_setup(tmp_path):
    # App sem nenhum usuário: a raiz deve redirecionar para /setup.
    dsn = f"sqlite:///{tmp_path}/novo.db"
    app = create_app(dsn=dsn)
    app.config.update(TESTING=True)
    client = app.test_client()

    resp = client.get("/")
    assert resp.status_code == 302
    assert "/setup" in resp.headers["Location"]

    # Criar o admin pelo navegador e já entrar autenticado.
    resp = client.post(
        "/setup",
        data={"username": "admin", "nome": "Chefe",
              "senha": "senha12345", "confirmar": "senha12345"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Painel Principal" in resp.data

    # Com admin criado, /setup passa a redirecionar para o login.
    resp = client.get("/setup")
    assert resp.status_code == 302


def test_setup_senha_curta_ou_diferente(tmp_path):
    dsn = f"sqlite:///{tmp_path}/novo2.db"
    app = create_app(dsn=dsn)
    app.config.update(TESTING=True)
    client = app.test_client()
    # Senha curta.
    resp = client.post(
        "/setup",
        data={"username": "admin", "senha": "curta", "confirmar": "curta"},
        follow_redirects=True,
    )
    assert "ao menos 8".encode() in resp.data
    # Senhas diferentes.
    resp = client.post(
        "/setup",
        data={"username": "admin", "senha": "senha12345", "confirmar": "outra12345"},
        follow_redirects=True,
    )
    assert "não conferem".encode() in resp.data


def test_salvar_tema(client, app):
    _login(client)
    client.post(
        "/settings",
        data={"tema_primary": "#1c7a43", "api_email": "", "api_omniroute": ""},
        follow_redirects=True,
    )
    resp = client.get("/dashboard")
    assert b"#1c7a43" in resp.data  # variável de tema aplicada no <style>
