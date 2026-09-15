"""Autenticação de contas de usuário (login/senha) do Informativo.

As senhas são gravadas **apenas como hash PBKDF2** (via Werkzeug), nunca em
texto puro. Os perfis são simples rótulos de texto — Administrador, Editor e
Auditor — alinhados às personas descritas na especificação do produto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .db import Database

# Perfis de acesso. Mantidos como constantes para uma única fonte de verdade.
PERFIS = ("Administrador", "Editor", "Auditor")


def hash_senha(senha: str) -> str:
    """Gera o hash PBKDF2-SHA256 da senha (com salt aleatório)."""
    if not senha or len(senha) < 8:
        raise ValueError("A senha deve ter ao menos 8 caracteres.")
    return generate_password_hash(senha, method="pbkdf2:sha256")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Confere a senha contra o hash armazenado (comparação constante)."""
    return check_password_hash(senha_hash, senha)


def normalizar_perfil(perfil: str) -> str:
    """Valida e normaliza o perfil informado."""
    perfil = (perfil or "").strip().title()
    if perfil not in PERFIS:
        raise ValueError(f"Perfil inválido: {perfil!r}. Use um de {PERFIS}.")
    return perfil


@dataclass
class ContaUsuario:
    """Registro de conta na tabela ``usuarios``."""

    id: int
    username: str
    perfil: str
    nome: Optional[str] = None
    ativo: bool = True


def _row_para_conta(row: dict[str, Any]) -> ContaUsuario:
    return ContaUsuario(
        id=row["id"],
        username=row["username"],
        perfil=row["perfil"],
        nome=row.get("nome"),
        ativo=bool(row.get("ativo", 1)),
    )


class UsuarioRepository:
    """Acesso à tabela ``usuarios`` (criação, busca e autenticação)."""

    def __init__(self, db: Database):
        self.db = db

    def _agora(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def existe(self, username: str) -> bool:
        total = self.db.scalar(
            "SELECT COUNT(*) FROM usuarios WHERE username = ?",
            (username.strip().lower(),),
        )
        return (total or 0) > 0

    def get(self, username: str) -> Optional[ContaUsuario]:
        row = self.db.query_one(
            "SELECT * FROM usuarios WHERE username = ?",
            (username.strip().lower(),),
        )
        return _row_para_conta(row) if row else None

    def criar(
        self,
        username: str,
        senha: str,
        perfil: str = "Editor",
        *,
        nome: Optional[str] = None,
        atualizar_se_existir: bool = False,
    ) -> ContaUsuario:
        """Cria (ou atualiza) uma conta. Levanta ``ValueError`` se já existir e
        ``atualizar_se_existir`` for ``False``."""
        username = username.strip().lower()
        if not username:
            raise ValueError("username é obrigatório")
        perfil = normalizar_perfil(perfil)
        senha_h = hash_senha(senha)
        agora = self._agora()

        if self.existe(username):
            if not atualizar_se_existir:
                raise ValueError(f"Usuário já existe: {username!r}")
            self.db.execute(
                "UPDATE usuarios SET senha_hash = ?, perfil = ?, nome = ?, "
                "atualizado_em = ? WHERE username = ?",
                (senha_h, perfil, nome, agora, username),
            )
        else:
            self.db.execute(
                "INSERT INTO usuarios (username, nome, perfil, senha_hash, "
                "ativo, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, nome, perfil, senha_h, 1, agora, agora),
            )
        self.db.commit()
        conta = self.get(username)
        assert conta is not None
        return conta

    def autenticar(self, username: str, senha: str) -> Optional[ContaUsuario]:
        """Valida credenciais. Retorna a conta ativa ou ``None`` se inválido."""
        row = self.db.query_one(
            "SELECT * FROM usuarios WHERE username = ?",
            (username.strip().lower(),),
        )
        if not row or not bool(row.get("ativo", 1)):
            return None
        if not verificar_senha(senha, row["senha_hash"]):
            return None
        return _row_para_conta(row)

    def listar(self) -> list[ContaUsuario]:
        return [
            _row_para_conta(r)
            for r in self.db.query_all("SELECT * FROM usuarios ORDER BY username")
        ]

    def set_ativo(self, username: str, ativo: bool) -> None:
        """Ativa ou desativa uma conta (desativada não consegue logar)."""
        self.db.execute(
            "UPDATE usuarios SET ativo = ?, atualizado_em = ? WHERE username = ?",
            (1 if ativo else 0, self._agora(), username.strip().lower()),
        )
        self.db.commit()

    def redefinir_senha(self, username: str, nova_senha: str) -> None:
        """Redefine a senha de uma conta existente (mantém perfil e nome)."""
        senha_h = hash_senha(nova_senha)
        self.db.execute(
            "UPDATE usuarios SET senha_hash = ?, atualizado_em = ? WHERE username = ?",
            (senha_h, self._agora(), username.strip().lower()),
        )
        self.db.commit()

    def definir_perfil(self, username: str, perfil: str) -> None:
        """Atualiza o perfil de acesso de uma conta."""
        perfil = normalizar_perfil(perfil)
        self.db.execute(
            "UPDATE usuarios SET perfil = ?, atualizado_em = ? WHERE username = ?",
            (perfil, self._agora(), username.strip().lower()),
        )
        self.db.commit()

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM usuarios") or 0)
