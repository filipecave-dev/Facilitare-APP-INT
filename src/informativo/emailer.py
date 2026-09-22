"""Configuração de e-mail por usuário e envio via SMTP.

Cada usuário pode ter a **sua própria conta de e-mail** para disparo dos
informativos e comunicados, seja qual for o provedor: Google (Gmail/Workspace),
Microsoft (Outlook/Office 365) ou um servidor próprio. A configuração é
genérica (SMTP para envio, IMAP opcional para leitura), com **presets** que
preenchem host/porta/segurança automaticamente.

O envio usa apenas a biblioteca padrão (``smtplib``), suportando conexões
``SSL`` (porta 465), ``STARTTLS`` (porta 587) ou sem criptografia.
"""

from __future__ import annotations

import secrets
import smtplib
import ssl
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

from .db import Database

# Presets por provedor: preenchem os campos técnicos automaticamente.
PRESETS = {
    "google": {
        "rotulo": "Google (Gmail / Workspace)",
        "smtp_host": "smtp.gmail.com", "smtp_porta": 587, "smtp_seguranca": "starttls",
        "imap_host": "imap.gmail.com", "imap_porta": 993, "imap_ssl": True,
        "ajuda": "Use uma Senha de app (com verificação em 2 etapas ativada).",
    },
    "microsoft": {
        "rotulo": "Microsoft (Outlook / Office 365)",
        "smtp_host": "smtp.office365.com", "smtp_porta": 587, "smtp_seguranca": "starttls",
        "imap_host": "outlook.office365.com", "imap_porta": 993, "imap_ssl": True,
        "ajuda": "Conta corporativa/Outlook; pode exigir senha de app.",
    },
    "outro": {
        "rotulo": "Outro (servidor próprio / IMAP-SMTP)",
        "smtp_host": "", "smtp_porta": 587, "smtp_seguranca": "starttls",
        "imap_host": "", "imap_porta": 993, "imap_ssl": True,
        "ajuda": "Informe os dados do seu provedor de e-mail.",
    },
}
SEGURANCAS = ("starttls", "ssl", "nenhuma")


class EmailError(Exception):
    """Falha ao configurar ou enviar e-mail."""


def gerar_senha(tamanho: int = 12) -> str:
    """Gera uma senha aleatória forte (letras, dígitos e símbolos seguros)."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%*-_"
    return "".join(secrets.choice(alfabeto) for _ in range(max(8, tamanho)))


@dataclass
class ConfigEmail:
    usuario_id: int
    provedor: str = "outro"
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_porta: int = 587
    smtp_seguranca: str = "starttls"
    smtp_usuario: Optional[str] = None
    smtp_senha: Optional[str] = None
    imap_host: Optional[str] = None
    imap_porta: int = 993
    imap_ssl: bool = True

    def configurado(self) -> bool:
        return bool(self.smtp_host and self.remetente_email and self.smtp_usuario)


def _row(r: dict) -> ConfigEmail:
    return ConfigEmail(
        usuario_id=r["usuario_id"],
        provedor=r.get("provedor") or "outro",
        remetente_nome=r.get("remetente_nome"),
        remetente_email=r.get("remetente_email"),
        smtp_host=r.get("smtp_host"),
        smtp_porta=int(r.get("smtp_porta") or 587),
        smtp_seguranca=r.get("smtp_seguranca") or "starttls",
        smtp_usuario=r.get("smtp_usuario"),
        smtp_senha=r.get("smtp_senha"),
        imap_host=r.get("imap_host"),
        imap_porta=int(r.get("imap_porta") or 993),
        imap_ssl=bool(r.get("imap_ssl", 1)),
    )


class EmailRepository:
    """Acesso à tabela ``usuario_email`` (uma configuração por usuário)."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, usuario_id: int) -> Optional[ConfigEmail]:
        r = self.db.query_one(
            "SELECT * FROM usuario_email WHERE usuario_id = ?", (usuario_id,)
        )
        return _row(r) if r else None

    def salvar(self, usuario_id: int, **campos) -> None:
        """Cria ou atualiza a configuração. A senha SMTP só é trocada se vier
        preenchida (deixe em branco para manter a atual)."""
        agora = datetime.now(timezone.utc).isoformat()
        atual = self.get(usuario_id)
        # A senha em branco preserva a existente.
        if not (campos.get("smtp_senha") or "").strip() and atual is not None:
            campos["smtp_senha"] = atual.smtp_senha
        dados = {
            "provedor": (campos.get("provedor") or "outro"),
            "remetente_nome": campos.get("remetente_nome"),
            "remetente_email": (campos.get("remetente_email") or "").strip() or None,
            "smtp_host": (campos.get("smtp_host") or "").strip() or None,
            "smtp_porta": int(campos.get("smtp_porta") or 587),
            "smtp_seguranca": campos.get("smtp_seguranca") or "starttls",
            "smtp_usuario": (campos.get("smtp_usuario") or "").strip() or None,
            "smtp_senha": campos.get("smtp_senha"),
            "imap_host": (campos.get("imap_host") or "").strip() or None,
            "imap_porta": int(campos.get("imap_porta") or 993),
            "imap_ssl": 1 if campos.get("imap_ssl") else 0,
        }
        if atual is None:
            cols = ", ".join(dados.keys())
            marks = ", ".join(["?"] * len(dados))
            self.db.execute(
                f"INSERT INTO usuario_email (usuario_id, {cols}, atualizado_em) "
                f"VALUES (?, {marks}, ?)",
                (usuario_id, *dados.values(), agora),
            )
        else:
            sets = ", ".join(f"{k} = ?" for k in dados)
            self.db.execute(
                f"UPDATE usuario_email SET {sets}, atualizado_em = ? WHERE usuario_id = ?",
                (*dados.values(), agora, usuario_id),
            )
        self.db.commit()

    def remover(self, usuario_id: int) -> None:
        self.db.execute("DELETE FROM usuario_email WHERE usuario_id = ?", (usuario_id,))
        self.db.commit()


def enviar_email(cfg: ConfigEmail, destinatario: str, assunto: str,
                 corpo_html: str, corpo_texto: Optional[str] = None,
                 *, timeout: int = 30) -> None:
    """Envia um e-mail via SMTP conforme a configuração. Levanta ``EmailError``.

    Suporta ``ssl`` (porta 465), ``starttls`` (587) e ``nenhuma``.
    """
    if not cfg.configurado():
        raise EmailError("Configuração de e-mail incompleta (host, remetente e usuário).")
    if not destinatario:
        raise EmailError("Destinatário não informado.")

    msg = EmailMessage()
    de = cfg.remetente_email
    if cfg.remetente_nome:
        de = f"{cfg.remetente_nome} <{cfg.remetente_email}>"
    msg["From"] = de
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content(corpo_texto or "Este e-mail requer um cliente com suporte a HTML.")
    msg.add_alternative(corpo_html, subtype="html")

    seguranca = (cfg.smtp_seguranca or "starttls").lower()
    try:
        if seguranca == "ssl":
            contexto = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_porta, timeout=timeout,
                                  context=contexto) as s:
                s.login(cfg.smtp_usuario, cfg.smtp_senha or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_porta, timeout=timeout) as s:
                s.ehlo()
                if seguranca == "starttls":
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if cfg.smtp_usuario:
                    s.login(cfg.smtp_usuario, cfg.smtp_senha or "")
                s.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Falha no envio SMTP: {exc}")
