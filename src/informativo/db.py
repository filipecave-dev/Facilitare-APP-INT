"""Camada fina de acesso a dados sobre ``sqlite3`` (biblioteca padrão).

O DSN aceito é ``sqlite:///caminho/arquivo.db`` (ou apenas um caminho de
arquivo). As linhas são devolvidas como dicionários (``sqlite3.Row``), o que
mantém o restante do código legível e independente da ordem das colunas.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterable, Optional, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    nome          TEXT,
    perfil        TEXT    NOT NULL DEFAULT 'Editor',
    senha_hash    TEXT    NOT NULL,
    ativo         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS fontes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL,
    url           TEXT    NOT NULL UNIQUE,
    categoria     TEXT,
    regiao        TEXT,
    idioma        TEXT,
    relevancia    INTEGER NOT NULL DEFAULT 3,
    prioridade    INTEGER NOT NULL DEFAULT 3,
    ativa         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS empresas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT    NOT NULL UNIQUE,
    nome_solucao  TEXT    NOT NULL,
    assunto_email TEXT    NOT NULL DEFAULT '',
    contato_email TEXT,
    tema_primary  TEXT,
    ativa         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""


def _caminho_do_dsn(dsn: str) -> str:
    """Extrai o caminho de arquivo de um DSN ``sqlite:///...`` ou de um path."""
    if dsn.startswith("sqlite:///"):
        return dsn[len("sqlite:///"):]
    if dsn.startswith("sqlite://"):
        return dsn[len("sqlite://"):]
    return dsn


class Database:
    """Conexão gerenciada com um banco SQLite.

    Uso típico::

        with Database("sqlite:///output/informativo.db") as db:
            init_db(db)
            db.query_all("SELECT * FROM fontes")
    """

    def __init__(self, dsn: str):
        caminho = _caminho_do_dsn(dsn)
        pasta = os.path.dirname(os.path.abspath(caminho))
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        self.conn = sqlite3.connect(caminho)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    # -- ciclo de vida ------------------------------------------------------
    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    # -- operações ----------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, tuple(params))

    def executescript(self, sql: str) -> None:
        self.conn.executescript(sql)

    def executemany(self, sql: str, seq_params: Iterable[Sequence[Any]]) -> None:
        self.conn.executemany(sql, [tuple(p) for p in seq_params])

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
        cur = self.conn.execute(sql, tuple(params))
        row = cur.fetchone()
        return dict(row) if row else None

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        cur = self.conn.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cur = self.conn.execute(sql, tuple(params))
        row = cur.fetchone()
        return row[0] if row else None


def init_db(db: Database) -> None:
    """Cria as tabelas do esquema, caso ainda não existam."""
    db.executescript(SCHEMA)
    db.commit()
