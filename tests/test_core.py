"""Testes de núcleo: banco, autenticação, fontes, tema e configurações."""

from __future__ import annotations

import pytest

from informativoli.auth import UsuarioRepository, hash_senha, verificar_senha
from informativoli.db import Database, init_db
from informativoli.fontes import FonteRepository, carregar_seed
from informativoli.settings_repo import SettingsRepository
from informativoli.themes import TEMA_PADRAO, normalizar_cor, tinta_de_contraste, variaveis_css


@pytest.fixture()
def db(tmp_path):
    dsn = f"sqlite:///{tmp_path}/teste.db"
    with Database(dsn) as conexao:
        init_db(conexao)
        yield conexao


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


# -- fontes -----------------------------------------------------------------
def test_seed_carrega_80_fontes():
    seed = carregar_seed()
    assert len(seed) == 80
    assert all(item["nome"] and item["url"] for item in seed)


def test_semear_se_vazio(db):
    repo = FonteRepository(db)
    inseridas = repo.semear_se_vazio()
    assert inseridas == 80
    assert repo.count() == 80
    # Idempotente: não duplica.
    assert repo.semear_se_vazio() == 0
    assert repo.count() == 80


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
