"""Configurações da aplicação (tabela ``configuracoes``).

Armazena pares chave/valor simples — como a cor de tema selecionada e as
chaves de integração (e-mail e Omniroute), que na v1 são apenas persistidas
para uso futuro pelas telas de envio de newsletter.
"""

from __future__ import annotations

from typing import Optional

from .db import Database


class SettingsRepository:
    """Leitura e escrita de configurações chave/valor."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, chave: str, padrao: Optional[str] = None) -> Optional[str]:
        row = self.db.query_one(
            "SELECT valor FROM configuracoes WHERE chave = ?", (chave,)
        )
        return row["valor"] if row else padrao

    def set(self, chave: str, valor: str) -> None:
        self.db.execute(
            "INSERT INTO configuracoes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )
        self.db.commit()

    def all(self) -> dict[str, str]:
        return {
            r["chave"]: r["valor"]
            for r in self.db.query_all("SELECT chave, valor FROM configuracoes")
        }
