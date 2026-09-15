"""Camada fina de acesso a dados, compatível com **SQLite** e **PostgreSQL**.

O backend é escolhido pelo DSN:

* ``sqlite:///caminho/arquivo.db`` (ou apenas um caminho de arquivo) → SQLite
  (biblioteca padrão). Ideal para desenvolvimento local e testes.
* ``postgresql://usuario:senha@host/banco`` (ou ``postgres://...``) → PostgreSQL
  via ``psycopg2``. Usado em produção (Render, Neon, etc.) para persistir
  usuários, senhas e demais dados entre deploys.

As linhas são sempre devolvidas como dicionários, e os SQLs usam ``?`` como
placeholder — traduzido para ``%s`` automaticamente no PostgreSQL.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterable, Optional, Sequence

# DDL comum aos dois bancos, exceto a definição da chave primária
# auto-incremento, que difere entre SQLite e PostgreSQL.
_TABELAS = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            {pk},
    username      TEXT    NOT NULL UNIQUE,
    nome          TEXT,
    perfil        TEXT    NOT NULL DEFAULT 'Editor',
    senha_hash    TEXT    NOT NULL,
    ativo         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS fontes (
    id            {pk},
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
    id            {pk},
    nome          TEXT    NOT NULL UNIQUE,
    nome_solucao  TEXT    NOT NULL,
    assunto_email TEXT    NOT NULL DEFAULT '',
    contato_email TEXT,
    tema_primary  TEXT,
    ativa         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS captacoes (
    id         {pk},
    fonte_id   INTEGER,
    fonte_nome TEXT,
    categoria  TEXT,
    regiao     TEXT,
    conteudo   TEXT,
    criado_em  TEXT
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""

SCHEMA_SQLITE = _TABELAS.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")
SCHEMA_POSTGRES = _TABELAS.format(pk="SERIAL PRIMARY KEY")


def _caminho_do_dsn(dsn: str) -> str:
    """Extrai o caminho de arquivo de um DSN ``sqlite:///...`` ou de um path."""
    if dsn.startswith("sqlite:///"):
        return dsn[len("sqlite:///"):]
    if dsn.startswith("sqlite://"):
        return dsn[len("sqlite://"):]
    return dsn


def _e_postgres(dsn: str) -> bool:
    return dsn.startswith("postgresql://") or dsn.startswith("postgres://")


class Database:
    """Conexão gerenciada com SQLite ou PostgreSQL.

    Uso típico::

        with Database(os.environ["INFORMATIVO_DSN"]) as db:
            init_db(db)
            db.query_all("SELECT * FROM fontes")
    """

    def __init__(self, dsn: str):
        if _e_postgres(dsn):
            self.backend = "postgres"
            import psycopg2  # importado só quando necessário
            import psycopg2.extras

            self._RealDict = psycopg2.extras.RealDictCursor
            self.conn = psycopg2.connect(dsn)
        else:
            self.backend = "sqlite"
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

    # -- tradução de placeholders ------------------------------------------
    def _traduzir(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.backend == "postgres" else sql

    def _cursor(self):
        if self.backend == "postgres":
            return self.conn.cursor(cursor_factory=self._RealDict)
        return self.conn.cursor()

    # -- operações ----------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()):
        cur = self._cursor()
        cur.execute(self._traduzir(sql), tuple(params))
        return cur

    def executescript(self, sql: str) -> None:
        if self.backend == "sqlite":
            self.conn.executescript(sql)
        else:
            cur = self._cursor()
            cur.execute(sql)

    def executemany(self, sql: str, seq_params: Iterable[Sequence[Any]]) -> None:
        cur = self._cursor()
        cur.executemany(self._traduzir(sql), [tuple(p) for p in seq_params])

    def insert(self, sql: str, params: Sequence[Any] = ()) -> Any:
        """Executa um INSERT e devolve o ``id`` gerado (portável)."""
        if self.backend == "postgres":
            cur = self.execute(sql + " RETURNING id", params)
            row = cur.fetchone()
            return row["id"] if row else None
        cur = self.execute(sql, params)
        return cur.lastrowid

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        cur = self.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        if self.backend == "postgres":
            return next(iter(row.values()))
        return row[0]


def init_db(db: Database) -> None:
    """Cria as tabelas do esquema, caso ainda não existam."""
    db.executescript(SCHEMA_POSTGRES if db.backend == "postgres" else SCHEMA_SQLITE)
    db.commit()
