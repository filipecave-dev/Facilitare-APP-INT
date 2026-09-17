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


def test_bootstrap_move_conteudo_atual_para_tivolitur(tmp_path):
    from informativo.empresas import EmpresaRepository
    from informativo.fontes import FonteRepository
    from informativo.omniroute import CaptacaoRepository

    dsn = f"sqlite:///{tmp_path}/tivo.db"
    # DB antigo com uma captação SEM empresa (conteúdo atual da plataforma).
    with Database(dsn) as db:
        init_db(db)
        f = FonteRepository(db).criar("Reuters", "reuters.com")
        CaptacaoRepository(db).registrar(f, "Conteúdo atual da plataforma.")
    # Ao subir o app, a empresa Tivolitur é criada e recebe o conteúdo atual.
    create_app(dsn=dsn)
    with Database(dsn) as db:
        tivo = EmpresaRepository(db).obter_por_nome("Tivolitur")
        assert tivo is not None
        cap = CaptacaoRepository(db).listar_recentes()[0]
        assert cap["empresa_id"] == tivo.id


def test_menu_enxuto_e_hub_configuracoes(client):
    _login(client)
    nav = client.get("/dashboard").data.decode()
    barra = nav[nav.find("mainnav"):nav.find("userbox")]
    # Menu inicial enxuto: só estes quatro itens.
    for item in ("Início", "Captação", "Informativo", "Configurações"):
        assert item in barra
    for fora in ("Fontes", "Usuários", "Empresas", "Auditoria", "Provedores"):
        assert fora not in barra
    # O hub reúne os módulos administrativos.
    hub = client.get("/configuracoes")
    assert hub.status_code == 200
    corpo = hub.data.decode()
    for modulo in ("Fontes", "Usuários", "Empresas", "Auditoria", "Provedores de IA"):
        assert modulo in corpo


def test_auditoria_abre(client):
    _login(client)
    resp = client.get("/auditoria")
    assert resp.status_code == 200
    assert b"Auditoria de IA" in resp.data


def test_salvar_cor_persiste_valor_customizado(client, app):
    from informativo.settings_repo import SettingsRepository

    _login(client)
    client.post("/settings", data={
        "tema_primary": "#8e44ad", "api_email": "",
        "ia_moeda": "US$", "ia_preco_in": "0.10",
        "ia_preco_out": "0.40", "ia_limite_diario": "1.00",
    }, follow_redirects=True)
    with Database(app.config["DSN"]) as db:
        assert SettingsRepository(db).get("tema_primary") == "#8e44ad"
    # e a cor volta refletida na página (campo oculto + CSS injetado)
    corpo = client.get("/settings").data.decode()
    assert 'id="tema-valor" value="#8e44ad"' in corpo
    assert "--primary: #8e44ad" in corpo


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


def test_editar_fonte(client, app):
    _login(client)
    from informativo.fontes import FonteRepository
    with Database(app.config["DSN"]) as db:
        fid = FonteRepository(db).criar("MinhaFonte", "minha.com", categoria="Geral").id
    resp = client.post(f"/fontes/{fid}/editar", data={
        "nome": "MinhaFonte Editada", "url": "minha.com",
        "categoria": "Segurança", "regiao": "Brasil", "idioma": "Português",
        "relevancia": "5", "prioridade": "4", "ativa": "1",
    }, follow_redirects=True)
    assert "atualizada".encode() in resp.data
    with Database(app.config["DSN"]) as db:
        f = FonteRepository(db).get(fid)
    assert f.nome == "MinhaFonte Editada"
    assert f.categoria == "Segurança" and f.relevancia == 5


def test_personificar_e_voltar(client, app):
    _login(client)  # admin
    from informativo.auth import UsuarioRepository
    with Database(app.config["DSN"]) as db:
        UsuarioRepository(db).criar("editor1", "senha12345", "Editor", nome="Editor Um")
    # personificar o editor
    resp = client.post("/usuarios/personificar", data={"username": "editor1"},
                       follow_redirects=True)
    assert b"editor1" in resp.data
    assert "personificação".encode() in resp.data  # banner no topo
    # no modo personificação, a rota de usuários (admin) é bloqueada
    assert client.get("/usuarios").status_code == 403
    # o aviso de personificação aparece
    assert "personificação".encode() in client.get("/dashboard").data
    # voltar ao acesso de admin
    resp = client.post("/usuarios/voltar", follow_redirects=True)
    assert client.get("/usuarios").status_code == 200


def test_admin_cria_usuario(client):
    _login(client)
    resp = client.post(
        "/usuarios/criar",
        data={"username": "editor1", "nome": "Editor Um",
              "perfil": "Editor", "senha": "senha12345"},
        follow_redirects=True,
    )
    assert b"editor1" in resp.data
    assert "criado".encode() in resp.data


def test_novo_usuario_consegue_logar(app):
    from informativo.auth import UsuarioRepository
    with Database(app.config["DSN"]) as db:
        UsuarioRepository(db).criar("suporte", "senha12345", "Auditor", nome="Suporte")
    c = app.test_client()
    resp = c.post("/", data={"username": "suporte", "senha": "senha12345"},
                  follow_redirects=True)
    assert b"Painel Principal" in resp.data


def test_editar_provedor(client, app):
    _login(client)
    client.post("/provedores/criar", data={
        "nome": "Gemini", "formato": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "modelo": "gemini-flash-latest", "api_key": "k1", "empresa_id": "", "ativo": "1",
    }, follow_redirects=True)
    from informativo.provedores import ProvedorRepository
    with Database(app.config["DSN"]) as db:
        pid = ProvedorRepository(db).listar()[0].id
    # edita o modelo, deixa a chave em branco (deve manter)
    resp = client.post(f"/provedores/{pid}/editar", data={
        "nome": "Gemini", "formato": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "modelo": "gemini-2.0-flash", "api_key": "", "empresa_id": "", "ativo": "1",
    }, follow_redirects=True)
    assert "atualizado".encode() in resp.data
    with Database(app.config["DSN"]) as db:
        p = ProvedorRepository(db).get(pid)
    assert p.modelo == "gemini-2.0-flash"
    assert p.api_key == "k1"  # chave preservada


def test_cadastrar_provedor_e_rodar_captacao(client, app, monkeypatch):
    _login(client)
    # cadastra um provedor de IA
    client.post("/provedores/criar", data={
        "nome": "OmniRoute DeepSeek", "formato": "openai",
        "base_url": "http://x:20128", "modelo": "deepseek-chat",
        "api_key": "k", "empresa_id": "", "ativo": "1",
    }, follow_redirects=True)
    # descobre o id do provedor e ATIVA as fontes (semente vem desativada)
    from informativo.provedores import ProvedorRepository
    from informativo.fontes import FonteRepository
    with Database(app.config["DSN"]) as db:
        pid = ProvedorRepository(db).listar()[0].id
        FonteRepository(db).definir_ativa_em_massa(True)
    # mocka a chamada ao modelo (retorna texto + uso de tokens)
    monkeypatch.setattr(
        "informativo.provedores.ClienteIA.chat_uso",
        lambda self, prompt, **kw: ("Resumo simulado da fonte.", {"in": 120, "out": 40}),
    )
    resp = client.post(
        "/captacao/rodar",
        data={"provedor_id": str(pid), "quantidade": "3", "regiao": "__BR__",
              "buscar_conteudo": "", "dias": "5"},
        follow_redirects=True,
    )
    assert "Captação concluída".encode() in resp.data
    assert "Resumo simulado da fonte.".encode() in resp.data
    # foco nacional: só fontes do Brasil foram captadas
    from informativo.omniroute import CaptacaoRepository
    with Database(app.config["DSN"]) as db:
        for c in CaptacaoRepository(db).listar_recentes(10):
            assert "brasil" in (c["regiao"] or "").lower()
    # a captação entra como pendente e pode ser aprovada
    from informativo.omniroute import CaptacaoRepository
    with Database(app.config["DSN"]) as db:
        cap = CaptacaoRepository(db)
        assert cap.contar_por_status()["pendente"] >= 1
        cid = cap.listar_recentes(1)[0]["id"]
    resp = client.post(f"/captacao/{cid}/aprovar", follow_redirects=True)
    with Database(app.config["DSN"]) as db:
        assert CaptacaoRepository(db).contar_por_status()["aprovada"] >= 1


def test_salvar_tema(client, app):
    _login(client)
    client.post(
        "/settings",
        data={"tema_primary": "#1c7a43", "api_email": "", "api_omniroute": ""},
        follow_redirects=True,
    )
    resp = client.get("/dashboard")
    assert b"#1c7a43" in resp.data  # variável de tema aplicada no <style>
