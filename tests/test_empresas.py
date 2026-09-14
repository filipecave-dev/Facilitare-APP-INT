"""Testes do cadastro de empresas (clientes) e do nome de saída."""

from __future__ import annotations

import pytest

from informativo.db import Database, init_db
from informativo.empresas import EmpresaRepository


@pytest.fixture()
def db(tmp_path):
    dsn = f"sqlite:///{tmp_path}/emp.db"
    with Database(dsn) as conexao:
        init_db(conexao)
        yield conexao


def test_criar_usa_nome_como_saida_padrao(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme Viagens")
    assert e.nome == "Acme Viagens"
    # Sem nome_saida informado, o padrão é o próprio nome da empresa.
    assert e.nome_saida == "Acme Viagens"


def test_criar_com_nome_de_saida_personalizado(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme Viagens", nome_saida="Acme Alertas", tema_primary="#1c7a43")
    assert e.nome_saida == "Acme Alertas"
    assert e.tema_primary == "#1c7a43"


def test_nome_duplicado(db):
    repo = EmpresaRepository(db)
    repo.criar("Acme")
    with pytest.raises(ValueError):
        repo.criar("acme")  # comparação sem diferenciar maiúsculas


def test_atualizar_nome_de_saida(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme")
    repo.atualizar(e.id, nome_saida="Boletim Acme")
    assert repo.get(e.id).nome_saida == "Boletim Acme"
    # Nome de saída vazio volta a acompanhar o nome da empresa.
    repo.atualizar(e.id, nome_saida="")
    assert repo.get(e.id).nome_saida == "Acme"


def test_alternar_e_remover(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme")
    assert repo.get(e.id).ativa is True
    repo.alternar_ativa(e.id)
    assert repo.get(e.id).ativa is False
    repo.remover(e.id)
    assert repo.get(e.id) is None
    assert repo.count() == 0
