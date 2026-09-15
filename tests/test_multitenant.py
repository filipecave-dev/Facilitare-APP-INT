"""Testes de isolamento multi-empresa (multi-tenant)."""

from __future__ import annotations

import pytest

from informativo.auth import UsuarioRepository
from informativo.db import Database, init_db
from informativo.empresas import EmpresaRepository
from informativo.fontes import FonteRepository
from informativo.omniroute import CaptacaoRepository
from informativo.provedores import ProvedorRepository
from informativo.web import create_app


@pytest.fixture()
def app(tmp_path):
    dsn = f"sqlite:///{tmp_path}/mt.db"
    aplicacao = create_app(dsn=dsn)
    aplicacao.config.update(TESTING=True)
    with Database(dsn) as db:
        init_db(db)
        # admin da plataforma (empresa_id None)
        UsuarioRepository(db).criar("admin", "senhaforte", "Administrador",
                                    nome="Admin", atualizar_se_existir=True)
    return aplicacao


def _login(app, username, senha):
    c = app.test_client()
    c.post("/", data={"username": username, "senha": senha}, follow_redirects=True)
    return c


def test_isolamento_de_captacoes(app):
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).criar("Empresa A")
        b = EmpresaRepository(db).criar("Empresa B")
        f = FonteRepository(db).listar()[0]
        cap = CaptacaoRepository(db)
        cap.registrar(f, "CONTEUDO DA A", provedor="X", empresa_id=a.id)
        cap.registrar(f, "CONTEUDO DA B", provedor="X", empresa_id=b.id)
        UsuarioRepository(db).criar("eda", "senha12345", "Editor", empresa_id=a.id)

    c = _login(app, "eda", "senha12345")
    resp = c.get("/captacao?status=pendente")
    assert b"CONTEUDO DA A" in resp.data
    assert b"CONTEUDO DA B" not in resp.data  # não vê a da outra empresa


def test_editor_nao_altera_provedor_global(app):
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).criar("Empresa A")
        g = ProvedorRepository(db).criar("Global", "openai", "http://x", "m")
        UsuarioRepository(db).criar("eda", "senha12345", "Editor", empresa_id=a.id)
        gid, aid = g.id, a.id

    c = _login(app, "eda", "senha12345")
    # não pode editar nem remover um provedor global
    assert c.get(f"/provedores/{gid}/editar").status_code == 403
    assert c.post(f"/provedores/{gid}/remover").status_code == 403
    # mas vê a lista (global como leitura) e cria o seu próprio (forçado à empresa)
    assert c.get("/provedores").status_code == 200
    c.post("/provedores/criar", data={
        "nome": "Meu", "formato": "openai", "base_url": "http://y",
        "modelo": "m", "api_key": "k", "ativo": "1",
    }, follow_redirects=True)
    with Database(app.config["DSN"]) as db:
        meus = [p for p in ProvedorRepository(db).listar() if p.nome == "Meu"]
    assert meus and meus[0].empresa_id == aid


def test_admin_de_empresa_ve_so_seus_usuarios(app):
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).criar("Empresa A")
        b = EmpresaRepository(db).criar("Empresa B")
        ur = UsuarioRepository(db)
        ur.criar("adma", "senha12345", "Administrador", empresa_id=a.id)
        ur.criar("edb", "senha12345", "Editor", empresa_id=b.id)

    c = _login(app, "adma", "senha12345")
    resp = c.get("/usuarios")
    assert b"adma" in resp.data
    assert b"edb" not in resp.data  # não vê usuário de outra empresa


def test_editor_nao_edita_fontes(app):
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).criar("Empresa A")
        fid = FonteRepository(db).listar()[0].id
        UsuarioRepository(db).criar("eda", "senha12345", "Editor", empresa_id=a.id)
    c = _login(app, "eda", "senha12345")
    # catálogo de fontes é global: edição é só da plataforma
    assert c.get(f"/fontes/{fid}/editar").status_code == 403
    assert c.get("/fontes").status_code == 200  # mas vê (leitura)


def test_config_e_empresas_sao_da_plataforma(app):
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).criar("Empresa A")
        UsuarioRepository(db).criar("adma", "senha12345", "Administrador", empresa_id=a.id)
    c = _login(app, "adma", "senha12345")
    assert c.get("/settings").status_code == 403       # tema global: só plataforma
    assert c.get("/empresas").status_code == 403        # lista de empresas: só plataforma
    # mas o admin da empresa edita a PRÓPRIA empresa
    with Database(app.config["DSN"]) as db:
        aid = EmpresaRepository(db).listar()[0].id
    assert c.get(f"/empresas/{aid}").status_code == 200
