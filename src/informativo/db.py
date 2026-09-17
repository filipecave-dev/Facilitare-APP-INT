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
    empresa_id    INTEGER,
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
    rss           TEXT,
    relevancia    INTEGER NOT NULL DEFAULT 3,
    prioridade    INTEGER NOT NULL DEFAULT 3,
    empresa_id    INTEGER,
    ativa         INTEGER NOT NULL DEFAULT 1,
    criado_em     TEXT,
    atualizado_em TEXT
);

CREATE TABLE IF NOT EXISTS fontes_candidatas (
    id         {pk},
    fonte_id   INTEGER,
    empresa_id INTEGER,
    nome       TEXT,
    url        TEXT,
    categoria  TEXT,
    regiao     TEXT,
    status     TEXT NOT NULL DEFAULT 'pendente',
    criado_em  TEXT
);

CREATE TABLE IF NOT EXISTS empresas (
    id             {pk},
    nome           TEXT    NOT NULL UNIQUE,
    nome_solucao   TEXT    NOT NULL,
    assunto_email  TEXT    NOT NULL DEFAULT '',
    contato_email  TEXT,
    tema_primary   TEXT,
    fonte_modelo   TEXT,
    template_nome  TEXT,
    template_mime  TEXT,
    template_dados TEXT,
    logo_nome      TEXT,
    logo_mime      TEXT,
    logo_dados     TEXT,
    ativa          INTEGER NOT NULL DEFAULT 1,
    criado_em      TEXT,
    atualizado_em  TEXT
);

CREATE TABLE IF NOT EXISTS provedores_ia (
    id         {pk},
    nome       TEXT    NOT NULL,
    formato    TEXT    NOT NULL DEFAULT 'openai',
    base_url   TEXT    NOT NULL,
    modelo     TEXT    NOT NULL,
    api_key    TEXT,
    empresa_id INTEGER,
    ativo      INTEGER NOT NULL DEFAULT 1,
    criado_em  TEXT
);

CREATE TABLE IF NOT EXISTS captacoes (
    id         {pk},
    fonte_id   INTEGER,
    fonte_nome TEXT,
    categoria  TEXT,
    regiao     TEXT,
    provedor   TEXT,
    empresa_id INTEGER,
    conteudo   TEXT,
    parafrase  TEXT,
    frente     TEXT,
    prioridade INTEGER NOT NULL DEFAULT 0,
    assinatura TEXT,
    status     TEXT NOT NULL DEFAULT 'pendente',
    criado_em  TEXT
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS uso_ia (
    id         {pk},
    dia        TEXT,
    empresa_id INTEGER,
    provedor   TEXT,
    operacao   TEXT,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    custo      REAL    NOT NULL DEFAULT 0,
    criado_em  TEXT
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


def _colunas_existentes(db: Database, tabela: str) -> set[str]:
    if db.backend == "postgres":
        rows = db.query_all(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (tabela,),
        )
        return {r["column_name"] for r in rows}
    rows = db.query_all(f"PRAGMA table_info({tabela})")
    return {r["name"] for r in rows}


def _garantir_coluna(db: Database, tabela: str, coluna: str, ddl: str) -> None:
    """Adiciona uma coluna se ela ainda não existir (migração leve, portável)."""
    if coluna not in _colunas_existentes(db, tabela):
        db.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {ddl}")
        db.commit()


def init_db(db: Database) -> None:
    """Cria as tabelas do esquema (caso não existam) e aplica migrações leves."""
    db.executescript(SCHEMA_POSTGRES if db.backend == "postgres" else SCHEMA_SQLITE)
    db.commit()
    # Migrações para bancos criados por versões anteriores (ex.: captacoes sem
    # as colunas de triagem). CREATE TABLE IF NOT EXISTS não altera colunas.
    _garantir_coluna(db, "captacoes", "categoria", "TEXT")
    _garantir_coluna(db, "captacoes", "regiao", "TEXT")
    _garantir_coluna(db, "captacoes", "provedor", "TEXT")
    _garantir_coluna(db, "captacoes", "status", "TEXT NOT NULL DEFAULT 'pendente'")
    _garantir_coluna(db, "captacoes", "empresa_id", "INTEGER")
    _garantir_coluna(db, "captacoes", "parafrase", "TEXT")
    _garantir_coluna(db, "captacoes", "frente", "TEXT")
    _garantir_coluna(db, "captacoes", "prioridade", "INTEGER NOT NULL DEFAULT 0")
    _garantir_coluna(db, "captacoes", "assinatura", "TEXT")
    _garantir_coluna(db, "provedores_ia", "empresa_id", "INTEGER")
    _garantir_coluna(db, "usuarios", "empresa_id", "INTEGER")
    _garantir_coluna(db, "fontes", "empresa_id", "INTEGER")
    _garantir_coluna(db, "fontes", "rss", "TEXT")
    _garantir_coluna(db, "empresas", "fonte_modelo", "TEXT")
    _garantir_coluna(db, "empresas", "template_nome", "TEXT")
    _garantir_coluna(db, "empresas", "template_mime", "TEXT")
    _garantir_coluna(db, "empresas", "template_dados", "TEXT")
    _garantir_coluna(db, "empresas", "logo_nome", "TEXT")
    _garantir_coluna(db, "empresas", "logo_mime", "TEXT")
    _garantir_coluna(db, "empresas", "logo_dados", "TEXT")
