"""Testes de núcleo: banco, autenticação, fontes, tema e configurações."""

from __future__ import annotations

import pytest

from informativo.auth import UsuarioRepository, hash_senha, verificar_senha
from informativo.db import Database, init_db
from informativo.fontes import FonteRepository, carregar_seed
from informativo.settings_repo import SettingsRepository
from informativo.themes import TEMA_PADRAO, normalizar_cor, tinta_de_contraste, variaveis_css


@pytest.fixture()
def db(tmp_path):
    dsn = f"sqlite:///{tmp_path}/teste.db"
    with Database(dsn) as conexao:
        init_db(conexao)
        yield conexao


# -- camada de banco (portabilidade) ----------------------------------------
def test_backend_sqlite_por_padrao(db):
    assert db.backend == "sqlite"
    # No SQLite os placeholders '?' não são traduzidos.
    assert db._traduzir("SELECT ? , ?") == "SELECT ? , ?"


def test_insert_retorna_id(db):
    from informativo.fontes import FonteRepository

    repo = FonteRepository(db)
    f1 = repo.criar("A", "a.com")
    f2 = repo.criar("B", "b.com")
    assert isinstance(f1.id, int) and f2.id == f1.id + 1


def test_traducao_placeholder_postgres(tmp_path, monkeypatch):
    # Sem conectar a um Postgres real: valida só a tradução ?->%s.
    import informativo.db as dbmod

    class _FakeDB(dbmod.Database):
        def __init__(self):  # não abre conexão
            self.backend = "postgres"

    fake = _FakeDB()
    assert fake._traduzir("WHERE nome = ? AND id <> ?") == "WHERE nome = %s AND id <> %s"


# -- senhas -----------------------------------------------------------------
def test_hash_e_verificacao_de_senha():
    h = hash_senha("segredo123")
    assert h != "segredo123"
    assert verificar_senha("segredo123", h)
    assert not verificar_senha("errada", h)


def test_hash_rejeita_senha_curta():
    with pytest.raises(ValueError):
        hash_senha("curta")


# -- usuários ---------------------------------------------------------------
def test_criar_e_autenticar_usuario(db):
    repo = UsuarioRepository(db)
    repo.criar("Admin", "senhaforte", "Administrador", nome="Chefe")
    assert repo.count() == 1
    conta = repo.autenticar("admin", "senhaforte")
    assert conta is not None
    assert conta.perfil == "Administrador"
    assert repo.autenticar("admin", "xxx") is None


def test_usuario_duplicado(db):
    repo = UsuarioRepository(db)
    repo.criar("joao", "senhaforte")
    with pytest.raises(ValueError):
        repo.criar("joao", "outrasenha")


def test_gestao_usuario_ativo_senha_perfil(db):
    repo = UsuarioRepository(db)
    repo.criar("maria", "senhaforte", "Editor")
    # desativar impede login
    repo.set_ativo("maria", False)
    assert repo.autenticar("maria", "senhaforte") is None
    repo.set_ativo("maria", True)
    assert repo.autenticar("maria", "senhaforte") is not None
    # redefinir senha
    repo.redefinir_senha("maria", "novasenha1")
    assert repo.autenticar("maria", "senhaforte") is None
    assert repo.autenticar("maria", "novasenha1") is not None
    # trocar perfil
    repo.definir_perfil("maria", "Auditor")
    assert repo.get("maria").perfil == "Auditor"


# -- fontes -----------------------------------------------------------------
def test_seed_carrega_80_fontes():
    seed = carregar_seed()
    assert len(seed) == 80
    assert all(item["nome"] and item["url"] for item in seed)


def test_seed_tem_rss_para_varias():
    seed = carregar_seed()
    com_rss = [i for i in seed if i.get("rss")]
    assert len(com_rss) >= 30  # feeds descobertos e cadastrados
    assert all(i["rss"].startswith("http") for i in com_rss)


def test_criar_e_backfill_rss(db):
    repo = FonteRepository(db)
    # cria a fonte SEM rss, com uma URL que existe na semente
    seed = carregar_seed()
    alvo = next(i for i in seed if i.get("rss"))
    f = repo.criar(alvo["nome"], alvo["url"])
    assert repo.get(f.id).rss in (None, "")
    # backfill preenche a partir da semente (casando pela URL)
    n = repo.backfill_rss_da_semente()
    assert n >= 1
    assert repo.get(f.id).rss == alvo["rss"]
    # e um rss explícito é preservado
    f2 = repo.criar("Custom", "custom.com", rss="https://custom.com/feed")
    assert repo.get(f2.id).rss == "https://custom.com/feed"


def test_semear_se_vazio(db):
    repo = FonteRepository(db)
    inseridas = repo.semear_se_vazio()
    assert inseridas == 80
    assert repo.count() == 80
    # Padrão: entram ATIVAS as fontes com RSS; sem RSS entram desativadas.
    ativas = [f for f in repo.listar() if f.ativa]
    assert len(ativas) >= 30
    assert all(f.rss for f in ativas)
    assert all(not f.ativa for f in repo.listar() if not f.rss)
    # Idempotente: não duplica.
    assert repo.semear_se_vazio() == 0
    assert repo.count() == 80


def test_ativar_com_rss_global(db):
    repo = FonteRepository(db)
    repo.semear_se_vazio()
    repo.definir_ativa_em_massa(False)  # zera tudo
    n = repo.ativar_com_rss_global()
    assert n >= 30
    ativas = [f for f in repo.listar() if f.ativa]
    assert ativas and all(f.rss and f.empresa_id is None for f in ativas)


def test_ativar_desativar_em_massa(db):
    repo = FonteRepository(db)
    repo.semear_se_vazio()
    repo.definir_ativa_em_massa(True)
    assert all(f.ativa for f in repo.listar())
    repo.definir_ativa_em_massa(False)
    assert all(not f.ativa for f in repo.listar())


def test_criar_normaliza_url_e_impede_duplicata(db):
    repo = FonteRepository(db)
    f = repo.criar("Exemplo", "exemplo.com")
    assert f.url == "https://exemplo.com"
    with pytest.raises(ValueError):
        repo.criar("Outro", "https://exemplo.com/")


def test_filtros_e_toggle(db):
    repo = FonteRepository(db)
    repo.semear_se_vazio()
    brasil = repo.listar(regiao="Brasil")
    assert len(brasil) > 0
    assert all(f.regiao == "Brasil" for f in brasil)

    busca = repo.listar(busca="Reuters")
    assert any("Reuters" in f.nome for f in busca)

    alvo = brasil[0]
    estado = alvo.ativa
    repo.alternar_ativa(alvo.id)
    assert repo.get(alvo.id).ativa != estado


def test_importar_ignora_existentes(db):
    repo = FonteRepository(db)
    repo.criar("Reuters", "https://www.reuters.com", categoria="Geral")
    resultado = repo.importar(carregar_seed())
    assert resultado["inseridas"] == 79
    assert resultado["ignoradas"] == 1


def test_remover(db):
    repo = FonteRepository(db)
    f = repo.criar("Temp", "temp.com")
    repo.remover(f.id)
    assert repo.get(f.id) is None


# -- tema -------------------------------------------------------------------
def test_normalizar_cor():
    assert normalizar_cor("#ff0000") == "#ff0000"
    assert normalizar_cor("vermelho") == TEMA_PADRAO
    assert normalizar_cor("#zzz") == TEMA_PADRAO


def test_tinta_de_contraste():
    assert tinta_de_contraste("#000000") == "#ffffff"
    assert tinta_de_contraste("#ffffff") == "#1c2431"


def test_variaveis_css_tem_chaves_essenciais():
    v = variaveis_css("#2557d6")
    assert v["--primary"] == "#2557d6"
    assert set(v) == {"--primary", "--primary-ink", "--badge-bg", "--badge-ink"}


# -- configurações ----------------------------------------------------------
def test_settings_get_set(db):
    repo = SettingsRepository(db)
    assert repo.get("inexistente", "padrao") == "padrao"
    repo.set("chave", "valor")
    assert repo.get("chave") == "valor"
    repo.set("chave", "novo")
    assert repo.get("chave") == "novo"
