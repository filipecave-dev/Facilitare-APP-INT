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


def test_criar_usa_nome_como_padrao(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme Viagens")
    assert e.nome == "Acme Viagens"
    # Sem nome_solucao informado, o padrão é o próprio nome da empresa.
    assert e.nome_solucao == "Acme Viagens"
    # Sem assunto_email informado, o padrão acompanha o nome da solução.
    assert e.assunto_email == "Acme Viagens"


def test_criar_com_nome_solucao_e_assunto_personalizados(db):
    repo = EmpresaRepository(db)
    e = repo.criar(
        "Acme Viagens",
        nome_solucao="Acme Alertas",
        assunto_email="Boletim de Viagem Acme",
        tema_primary="#1c7a43",
    )
    assert e.nome_solucao == "Acme Alertas"
    assert e.assunto_email == "Boletim de Viagem Acme"
    assert e.tema_primary == "#1c7a43"


def test_assunto_padrao_acompanha_nome_solucao(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme", nome_solucao="Acme Alertas")
    assert e.assunto_email == "Acme Alertas"


def test_nome_duplicado(db):
    repo = EmpresaRepository(db)
    repo.criar("Acme")
    with pytest.raises(ValueError):
        repo.criar("acme")  # comparação sem diferenciar maiúsculas


def test_atualizar_nome_solucao_e_assunto(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme")
    repo.atualizar(e.id, nome_solucao="Boletim Acme", assunto_email="Alertas de hoje")
    atual = repo.get(e.id)
    assert atual.nome_solucao == "Boletim Acme"
    assert atual.assunto_email == "Alertas de hoje"
    # Campos vazios voltam aos padrões (solução -> nome; assunto -> solução).
    repo.atualizar(e.id, nome_solucao="", assunto_email="")
    atual = repo.get(e.id)
    assert atual.nome_solucao == "Acme"
    assert atual.assunto_email == "Acme"


def test_alternar_e_remover(db):
    repo = EmpresaRepository(db)
    e = repo.criar("Acme")
    assert repo.get(e.id).ativa is True
    repo.alternar_ativa(e.id)
    assert repo.get(e.id).ativa is False
    repo.remover(e.id)
    assert repo.get(e.id) is None
    assert repo.count() == 0
