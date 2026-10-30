"""Proteção da senha SMTP gravada no ``config.json``.

No Windows usa o DPAPI (``win32crypt``, do pywin32): a senha só pode ser lida
pelo mesmo usuário do Windows, no mesmo computador. Fora do Windows (testes)
grava apenas codificada em base64.
"""

from __future__ import annotations

import base64
import sys

_DPAPI = "dpapi:"
_B64 = "b64:"


def proteger(senha: str) -> str:
    if not senha:
        return ""
    if sys.platform == "win32":
        try:
            import win32crypt
            dados = win32crypt.CryptProtectData(senha.encode("utf-8"), "Disparo de Laminas",
                                                None, None, None, 0)
            return _DPAPI + base64.b64encode(dados).decode("ascii")
        except Exception:  # noqa: BLE001 - sem pywin32: cai para base64
            pass
    return _B64 + base64.b64encode(senha.encode("utf-8")).decode("ascii")


def revelar(valor: str) -> str:
    if not valor:
        return ""
    if valor.startswith(_DPAPI):
        import win32crypt
        _, dados = win32crypt.CryptUnprotectData(base64.b64decode(valor[len(_DPAPI):]),
                                                 None, None, None, 0)
        return dados.decode("utf-8")
    if valor.startswith(_B64):
        return base64.b64decode(valor[len(_B64):]).decode("utf-8")
    return valor  # texto puro (editado à mão no config.json)
