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


def test_painel_isola_resultados_por_empresa(app):
    """Usuário vinculado a uma empresa vê no painel só os dados dela; o
    Administrador da plataforma vê tudo e pode filtrar por empresa."""
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).obter_ou_criar("Tivolitur")
        b = EmpresaRepository(db).criar("Bortoluzzi Mourao")
        f = FonteRepository(db).listar()[0]
        cap = CaptacaoRepository(db)
        # textos bem distintos p/ não colidir com a deduplicação
        for t in ("Alfa greve aeroporto Guarulhos hoje",
                  "Beta enchente litoral norte agora"):
            cap.registrar(f, t + " Tivolitur", provedor="X", empresa_id=a.id)
        for t in ("Gama feira gastronomia centro cidade",
                  "Delta congresso mercado imobiliario nacional",
                  "Epsilon rodovia interditada serra montanha"):
            cap.registrar(f, t + " Bortoluzzi", provedor="X", empresa_id=b.id)
        UsuarioRepository(db).criar("filipe", "senha12345", "Editor", empresa_id=a.id)

        cap_a = cap.metricas(empresa_id=a.id, somente_empresa=True)["captadas"]
        cap_b = cap.metricas(empresa_id=b.id, somente_empresa=True)["captadas"]
        cap_tudo = cap.metricas()["captadas"]
    assert cap_a == 2 and cap_b == 3 and cap_tudo == 5

    # Usuário da Tivolitur: painel só com dados da Tivolitur, sem controles de plataforma
    c = _login(app, "filipe", "senha12345")
    dash = c.get("/dashboard").data
    assert b"Bortoluzzi" not in dash
    assert b"Filtrar por empresa" not in dash  # sem seletor de plataforma
    # e a curva ABC também é escopada (só a fonte usada pela Tivolitur, se houver)
    cap_view = c.get("/captacao?status=pendente").data
    assert b"Tivolitur" in cap_view and b"Bortoluzzi" not in cap_view
    assert b"Atribuir empresa" not in cap_view  # sem atribuição em massa (plataforma)


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


def test_fonte_privada_isolada_e_curadoria(app):
    from informativo.fontes import CandidataRepository, FonteRepository
    with Database(app.config["DSN"]) as db:
        a = EmpresaRepository(db).criar("Empresa A")
        b = EmpresaRepository(db).criar("Empresa B")
        UsuarioRepository(db).criar("eda", "senha12345", "Editor", empresa_id=a.id)
        UsuarioRepository(db).criar("edb", "senha12345", "Editor", empresa_id=b.id)
        aid = a.id

    # Editor da A cria uma fonte privada
    ca = _login(app, "eda", "senha12345")
    ca.post("/fontes/adicionar", data={
        "nome": "Fonte Secreta A", "url": "https://secreta-a.com",
        "categoria": "Geral", "regiao": "Brasil", "relevancia": "3", "prioridade": "3",
    }, follow_redirects=True)

    with Database(app.config["DSN"]) as db:
        fr = FonteRepository(db)
        secretas = [f for f in fr.listar() if f.nome == "Fonte Secreta A"]
        assert secretas and secretas[0].empresa_id == aid  # privada da A
        # virou candidata na curadoria
        assert CandidataRepository(db).contar_pendentes() == 1

    # Editor da B NÃO vê a fonte privada da A
    cb = _login(app, "edb", "senha12345")
    resp = cb.get("/fontes")
    assert b"Fonte Secreta A" not in resp.data

    # Plataforma vê na curadoria e promove ao global
    cadmin = _login(app, "admin", "senhaforte")
    resp = cadmin.get("/curadoria?status=pendente")
    assert b"Fonte Secreta A" in resp.data
    with Database(app.config["DSN"]) as db:
        cid = CandidataRepository(db).listar(status="pendente")[0]["id"]
    cadmin.post(f"/curadoria/{cid}/promover", follow_redirects=True)
    with Database(app.config["DSN"]) as db:
        f = [f for f in FonteRepository(db).listar() if f.nome == "Fonte Secreta A"][0]
        assert f.empresa_id is None  # agora é global
    # Agora a empresa B vê (é global)
    assert b"Fonte Secreta A" in cb.get("/fontes").data


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
