"""Senha do SMTP guardada nas **Chaves do macOS** (Keychain).

O ``config.json`` guarda só uma referência (``keychain:<usuário>``); a senha
fica no app Acesso às Chaves, protegida pela senha do usuário do Mac. Usa o
pacote ``keyring``; sem ele (ou fora do Mac, nos testes) grava apenas
codificada em base64.
"""

from __future__ import annotations

import base64

SERVICO = "Sistema de Envio - SMTP"
_CHAVES = "keychain:"
_B64 = "b64:"
_DPAPI = "dpapi:"  # senha protegida no Windows: não pode ser lida no Mac


def proteger(senha: str, conta: str = "") -> str:
    """Guarda a senha e devolve o que vai para o ``config.json``."""
    if not senha:
        return ""
    conta = conta or "smtp"
    try:
        import keyring
        keyring.set_password(SERVICO, conta, senha)
        if keyring.get_password(SERVICO, conta) == senha:
            return _CHAVES + conta
    except Exception:  # noqa: BLE001 - sem Chaves disponíveis: cai para base64
        pass
    return _B64 + base64.b64encode(senha.encode("utf-8")).decode("ascii")


def revelar(valor: str) -> str:
    if not valor or valor.startswith(_DPAPI):
        return ""
    if valor.startswith(_CHAVES):
        try:
            import keyring
            return keyring.get_password(SERVICO, valor[len(_CHAVES):]) or ""
        except Exception:  # noqa: BLE001 - Chaves indisponíveis
            return ""
    if valor.startswith(_B64):
        return base64.b64decode(valor[len(_B64):]).decode("utf-8")
    return valor  # texto puro (editado à mão no config.json)


def esquecer(valor: str) -> None:
    """Apaga a senha das Chaves (ao trocar de usuário SMTP)."""
    if valor.startswith(_CHAVES):
        try:
            import keyring
            keyring.delete_password(SERVICO, valor[len(_CHAVES):])
        except Exception:  # noqa: BLE001 - já não existe
            pass
