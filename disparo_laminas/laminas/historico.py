"""Histórico de envios (lista de Enviados) em SQLite.

O histórico é a fonte da verdade para o controle: impede reenvio ao mesmo
e-mail, conta o limite diário e pode ser exportado para Excel. Um arquivo
SQLite é usado (e não a própria planilha) porque não fica travado quando a
planilha está aberta no Excel durante o disparo.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from .base import normalizar_email

ENVIADO = "Enviado"
ERRO = "Erro"
IMPORTADO = "Importado"
# Status que contam como "este e-mail já recebeu lâmina".
_JA_RECEBEU = (ENVIADO, IMPORTADO)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS envios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora   TEXT,
    empresa     TEXT,
    nome        TEXT,
    email       TEXT NOT NULL,
    email_norm  TEXT NOT NULL,
    cc          TEXT,
    campanha    TEXT,
    lamina      TEXT,
    anexo       TEXT,
    assunto     TEXT,
    status      TEXT NOT NULL,
    erro        TEXT
);
CREATE INDEX IF NOT EXISTS ix_envios_email ON envios (email_norm);
CREATE INDEX IF NOT EXISTS ix_envios_data ON envios (data_hora);
"""

COLUNAS_EXPORTACAO = [
    ("data_hora", "Data/Hora"), ("empresa", "Empresa"), ("nome", "Nome"),
    ("email", "E-mail"), ("cc", "Cópia (CC)"), ("campanha", "Campanha"),
    ("lamina", "Lâmina"), ("anexo", "Anexo"), ("assunto", "Assunto"), ("status", "Status"), ("erro", "Erro"),
]


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Historico:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conectar()) as con, con:
            con.executescript(_ESQUEMA)
            colunas = {r["name"] for r in con.execute("PRAGMA table_info(envios)")}
            if "anexo" not in colunas:  # histórico criado antes do anexo
                con.execute("ALTER TABLE envios ADD COLUMN anexo TEXT")

    def _conectar(self) -> sqlite3.Connection:
        # Uma conexão por operação: o disparo roda em outra thread.
        con = sqlite3.connect(self.caminho, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    # -- consultas ---------------------------------------------------------
    def ja_enviados(self) -> dict[str, Optional[str]]:
        """E-mail normalizado -> data/hora do primeiro envio."""
        with closing(self._conectar()) as con:
            linhas = con.execute(
                "SELECT email_norm, MIN(data_hora) AS quando FROM envios "
                f"WHERE status IN ({','.join('?' * len(_JA_RECEBEU))}) GROUP BY email_norm",
                _JA_RECEBEU,
            ).fetchall()
        return {r["email_norm"]: r["quando"] for r in linhas}

    def data_envio(self, email: str) -> Optional[str]:
        """Data/hora do primeiro envio para o e-mail, ``""`` se só houver
        registro sem data, ou ``None`` se nunca recebeu."""
        with closing(self._conectar()) as con:
            r = con.execute(
                "SELECT COUNT(*) AS n, MIN(data_hora) AS quando FROM envios "
                f"WHERE email_norm = ? AND status IN ({','.join('?' * len(_JA_RECEBEU))})",
                (normalizar_email(email), *_JA_RECEBEU),
            ).fetchone()
        if not r["n"]:
            return None
        return r["quando"] or ""

    def enviados_no_dia(self, dia: Optional[date] = None) -> int:
        dia = dia or date.today()
        with closing(self._conectar()) as con:
            r = con.execute(
                "SELECT COUNT(*) FROM envios WHERE status = ? AND data_hora LIKE ?",
                (ENVIADO, f"{dia.isoformat()}%"),
            ).fetchone()
        return int(r[0])

    def listar(self, busca: str = "") -> list[dict]:
        sql = "SELECT * FROM envios"
        params: tuple = ()
        if busca:
            sql += (" WHERE email LIKE ? OR nome LIKE ? OR empresa LIKE ?"
                    " OR campanha LIKE ? OR status LIKE ? OR data_hora LIKE ?")
            params = (f"%{busca}%",) * 6
        sql += " ORDER BY COALESCE(data_hora, '') DESC, id DESC"
        with closing(self._conectar()) as con:
            return [dict(r) for r in con.execute(sql, params).fetchall()]

    # -- gravação ----------------------------------------------------------
    def registrar(self, *, email: str, nome: str = "", empresa: str = "", cc: str = "",
                  campanha: str = "", lamina: str = "", anexo: str = "", assunto: str = "",
                  status: str = ENVIADO, erro: str = "", data_hora: Optional[str] = None) -> None:
        with closing(self._conectar()) as con, con:
            con.execute(
                "INSERT INTO envios (data_hora, empresa, nome, email, email_norm, cc,"
                " campanha, lamina, anexo, assunto, status, erro)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data_hora or _agora(), empresa, nome, email, normalizar_email(email), cc,
                 campanha, lamina, anexo, assunto, status, erro),
            )

    def importar(self, regs: Iterable[dict], origem: str = "") -> tuple[int, int]:
        """Importa envios feitos antes (ex.: abas RELATORIO/BASE-ENVIADO da
        macro antiga) para que entrem no controle de duplicados.

        Retorna ``(importados, ignorados)``. São ignorados e-mails inválidos,
        já existentes no histórico e linhas com status de erro.
        """
        existentes = set(self.ja_enviados())
        novos = []
        ignorados = 0
        for reg in regs:
            norm = normalizar_email(reg.get("email"))
            status = (reg.get("status") or "").lower()
            if not norm or "@" not in norm or norm in existentes or (status and "envi" not in status):
                ignorados += 1
                continue
            existentes.add(norm)
            quando = reg.get("data")
            novos.append((
                quando.strftime("%Y-%m-%d %H:%M:%S") if quando else None,
                reg.get("empresa", ""), reg.get("nome", ""), reg["email"], norm,
                "", "", "", "", IMPORTADO, origem,
            ))
        with closing(self._conectar()) as con, con:
            con.executemany(
                "INSERT INTO envios (data_hora, empresa, nome, email, email_norm, cc,"
                " campanha, lamina, assunto, status, erro)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                novos,
            )
        return len(novos), ignorados

    # -- exportação --------------------------------------------------------
    def exportar_xlsx(self, destino: str | Path) -> int:
        from openpyxl import Workbook
        from openpyxl.styles import Font

        linhas = self.listar()
        wb = Workbook()
        ws = wb.active
        ws.title = "ENVIADOS"
        ws.append([titulo for _, titulo in COLUNAS_EXPORTACAO])
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in linhas:
            ws.append([r.get(chave) or "" for chave, _ in COLUNAS_EXPORTACAO])
        larguras = {"A": 20, "B": 30, "C": 28, "D": 36, "E": 30, "F": 16, "G": 28, "H": 36,
                    "I": 50, "J": 11, "K": 30}
        for col, largura in larguras.items():
            ws.column_dimensions[col].width = largura
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        wb.save(destino)
        return len(linhas)
