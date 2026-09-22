"""Testes da configuração de e-mail por usuário e do envio SMTP."""

from __future__ import annotations

import pytest

from informativo.auth import UsuarioRepository
from informativo.db import Database, init_db
from informativo.emailer import (
    PRESETS, ConfigEmail, EmailError, EmailRepository, enviar_email, gerar_senha,
)


@pytest.fixture()
def db(tmp_path):
    with Database(f"sqlite:///{tmp_path}/e.db") as conexao:
        init_db(conexao)
        yield conexao


def test_presets_tem_google_microsoft_outro():
    assert set(PRESETS) >= {"google", "microsoft", "outro"}
    assert PRESETS["google"]["smtp_host"] == "smtp.gmail.com"
    assert PRESETS["microsoft"]["smtp_porta"] == 587


def test_gerar_senha_forte():
    s = gerar_senha(12)
    assert len(s) == 12
    assert gerar_senha(4) and len(gerar_senha(4)) >= 8  # piso de 8


def test_repo_salvar_get_remover_preserva_senha(db):
    u = UsuarioRepository(db).criar("joao", "senhaforte", "Editor")
    repo = EmailRepository(db)
    assert repo.get(u.id) is None
    repo.salvar(u.id, provedor="google", remetente_email="j@x.com",
                smtp_host="smtp.gmail.com", smtp_porta=587, smtp_seguranca="starttls",
                smtp_usuario="j@x.com", smtp_senha="segredo", imap_ssl=True)
    cfg = repo.get(u.id)
    assert cfg.smtp_host == "smtp.gmail.com" and cfg.smtp_senha == "segredo"
    assert cfg.configurado() is True
    # salvar sem senha preserva a existente
    repo.salvar(u.id, provedor="google", remetente_email="j@x.com",
                smtp_host="smtp.gmail.com", smtp_usuario="j@x.com", smtp_senha="")
    assert repo.get(u.id).smtp_senha == "segredo"
    repo.remover(u.id)
    assert repo.get(u.id) is None


def test_enviar_email_incompleto_levanta(db):
    cfg = ConfigEmail(usuario_id=1)  # sem host/remetente
    with pytest.raises(EmailError):
        enviar_email(cfg, "a@b.com", "oi", "<p>oi</p>")


def test_enviar_email_starttls_usa_smtp(monkeypatch):
    enviados = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            enviados["host"] = host; enviados["port"] = port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, context=None): enviados["starttls"] = True
        def login(self, u, p): enviados["login"] = (u, p)
        def send_message(self, msg): enviados["to"] = msg["To"]

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    cfg = ConfigEmail(usuario_id=1, remetente_email="de@x.com", smtp_host="smtp.x.com",
                      smtp_porta=587, smtp_seguranca="starttls", smtp_usuario="de@x.com",
                      smtp_senha="p")
    enviar_email(cfg, "para@y.com", "Assunto", "<p>corpo</p>", "corpo")
    assert enviados["host"] == "smtp.x.com" and enviados["starttls"] is True
    assert enviados["to"] == "para@y.com" and enviados["login"] == ("de@x.com", "p")
