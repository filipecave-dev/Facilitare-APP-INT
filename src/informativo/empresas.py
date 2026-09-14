"""Cadastro de empresas (clientes) do Informativo.

Cada **empresa** é um cliente cadastrado dentro do sistema. Além do nome de
cadastro, cada empresa personaliza o seu **nome de saída** (``nome_saida``) — o
nome exibido no informativo/newsletter que ela envia — e, opcionalmente, uma
cor de destaque própria (``tema_primary``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .db import Database


@dataclass
class Empresa:
    """Registro da tabela ``empresas``."""

    id: int
    nome: str
    nome_saida: str
    contato_email: Optional[str] = None
    tema_primary: Optional[str] = None
    ativa: bool = True
    criado_em: Optional[str] = None
    atualizado_em: Optional[str] = None


def _row_para_empresa(row: dict) -> Empresa:
    return Empresa(
        id=row["id"],
        nome=row["nome"],
        nome_saida=row["nome_saida"],
        contato_email=row.get("contato_email"),
        tema_primary=row.get("tema_primary"),
        ativa=bool(row.get("ativa", 1)),
        criado_em=row.get("criado_em"),
        atualizado_em=row.get("atualizado_em"),
    )


class EmpresaRepository:
    """Acesso à tabela ``empresas`` (CRUD)."""

    def __init__(self, db: Database):
        self.db = db

    def _agora(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- leitura ------------------------------------------------------------
    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM empresas") or 0)

    def get(self, empresa_id: int) -> Optional[Empresa]:
        row = self.db.query_one("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
        return _row_para_empresa(row) if row else None

    def existe_nome(self, nome: str, ignorar_id: Optional[int] = None) -> bool:
        if ignorar_id is None:
            total = self.db.scalar(
                "SELECT COUNT(*) FROM empresas WHERE nome = ? COLLATE NOCASE",
                (nome.strip(),),
            )
        else:
            total = self.db.scalar(
                "SELECT COUNT(*) FROM empresas WHERE nome = ? COLLATE NOCASE AND id <> ?",
                (nome.strip(), ignorar_id),
            )
        return (total or 0) > 0

    def listar(self, *, apenas_ativas: bool = False) -> list[Empresa]:
        sql = "SELECT * FROM empresas"
        if apenas_ativas:
            sql += " WHERE ativa = 1"
        sql += " ORDER BY nome COLLATE NOCASE ASC"
        return [_row_para_empresa(r) for r in self.db.query_all(sql)]

    # -- escrita ------------------------------------------------------------
    def criar(
        self,
        nome: str,
        *,
        nome_saida: Optional[str] = None,
        contato_email: Optional[str] = None,
        tema_primary: Optional[str] = None,
        ativa: bool = True,
    ) -> Empresa:
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("O nome da empresa é obrigatório.")
        if self.existe_nome(nome):
            raise ValueError(f"Já existe uma empresa com o nome {nome!r}.")
        # Por padrão, o nome de saída começa igual ao nome da empresa.
        nome_saida = (nome_saida or "").strip() or nome
        agora = self._agora()
        cur = self.db.execute(
            "INSERT INTO empresas (nome, nome_saida, contato_email, tema_primary, "
            "ativa, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nome, nome_saida, contato_email, tema_primary,
             1 if ativa else 0, agora, agora),
        )
        self.db.commit()
        empresa = self.get(cur.lastrowid)
        assert empresa is not None
        return empresa

    def atualizar(self, empresa_id: int, **campos) -> None:
        permitidos = {"nome", "nome_saida", "contato_email", "tema_primary", "ativa"}
        empresa = self.get(empresa_id)
        if empresa is None:
            raise ValueError("Empresa não encontrada.")
        if "nome" in campos:
            novo = (campos["nome"] or "").strip()
            if not novo:
                raise ValueError("O nome da empresa é obrigatório.")
            if self.existe_nome(novo, ignorar_id=empresa_id):
                raise ValueError(f"Já existe uma empresa com o nome {novo!r}.")
        if "nome_saida" in campos:
            # Nome de saída vazio volta a acompanhar o nome da empresa.
            campos["nome_saida"] = (campos["nome_saida"] or "").strip() or (
                (campos.get("nome") or empresa.nome).strip()
            )
        sets, params = [], []
        for chave, valor in campos.items():
            if chave not in permitidos:
                continue
            if chave == "ativa":
                valor = 1 if valor else 0
            sets.append(f"{chave} = ?")
            params.append(valor)
        if not sets:
            return
        sets.append("atualizado_em = ?")
        params.append(self._agora())
        params.append(empresa_id)
        self.db.execute(
            f"UPDATE empresas SET {', '.join(sets)} WHERE id = ?", params
        )
        self.db.commit()

    def alternar_ativa(self, empresa_id: int) -> None:
        self.db.execute(
            "UPDATE empresas SET ativa = 1 - ativa, atualizado_em = ? WHERE id = ?",
            (self._agora(), empresa_id),
        )
        self.db.commit()

    def remover(self, empresa_id: int) -> None:
        self.db.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        self.db.commit()
