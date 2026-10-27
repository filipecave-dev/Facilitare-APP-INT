"""Montagem do e-mail: campos variáveis, saudação e corpo HTML com a lâmina."""

from __future__ import annotations

import html
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import Contato

CAMPOS_AJUDA = "{nome}  {primeiro_nome}  {empresa}  {saudacao}"


@dataclass
class Email:
    para: str
    assunto: str
    texto_inicio: str
    texto_fim: str
    cc: str = ""
    cco: str = ""
    imagem: Optional[Path] = None
    anexos: list[Path] = field(default_factory=list)


def saudacao(agora: datetime) -> str:
    """Mesma regra da macro: antes do meio-dia "bom dia", depois "boa tarde"."""
    return "bom dia" if agora.hour < 12 else "boa tarde"


def preencher(texto: str, contato: Contato, agora: datetime) -> str:
    """Troca os campos variáveis pelo dado do contato.

    Aceita também os marcadores da planilha antiga (``<<Nome do Cliente>>`` e
    ``<diatarde>``).
    """
    valores = {
        "nome": contato.nome,
        "primeiro_nome": contato.nome.split()[0] if contato.nome else "",
        "empresa": contato.empresa,
        "saudacao": saudacao(agora),
    }
    texto = (texto or "").replace("<<Nome do Cliente>>", "{nome}").replace("<diatarde>", "{saudacao}")
    return re.sub(r"\{(\w+)\}", lambda m: valores.get(m.group(1), m.group(0)), texto)


def montar(contato: Contato, mensagem: dict, *, imagem: Optional[Path], cc: str = "",
           cco: str = "", anexos: Optional[list[Path]] = None,
           agora: Optional[datetime] = None) -> Email:
    agora = agora or datetime.now()
    return Email(
        para=contato.email,
        assunto=preencher(mensagem.get("assunto", ""), contato, agora),
        texto_inicio=preencher(mensagem.get("texto_inicio", ""), contato, agora),
        texto_fim=preencher(mensagem.get("texto_fim", ""), contato, agora),
        cc=cc if contato.cc else "",
        cco=cco,
        imagem=imagem,
        anexos=list(anexos or []),
    )


# -- HTML --------------------------------------------------------------------

_ESTILO = "font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#000000"


def _paragrafos(texto: str) -> str:
    if not texto.strip():
        return ""
    corpo = html.escape(texto.strip("\n")).replace("\n", "<br>\n")
    return f'<p style="{_ESTILO};margin:0 0 12px 0">{corpo}</p>\n'


def dimensoes_imagem(caminho: Path) -> Optional[tuple[int, int]]:
    """(largura, altura) de PNG/GIF/JPEG lendo só o cabeçalho do arquivo."""
    try:
        with open(caminho, "rb") as f:
            dados = f.read(26)
            if dados[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", dados[16:24])
            if dados[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", dados[6:10])
            if dados[:2] != b"\xff\xd8":
                return None
            f.seek(2)
            while True:
                marcador = f.read(2)
                if len(marcador) < 2 or marcador[0] != 0xFF:
                    return None
                if marcador[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                                   0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    f.read(3)
                    altura, largura = struct.unpack(">HH", f.read(4))
                    return largura, altura
                tamanho = struct.unpack(">H", f.read(2))[0]
                f.seek(tamanho - 2, 1)
    except (OSError, struct.error):
        return None


def corpo_html(email: Email, src_imagem: Optional[str], largura_max: int) -> str:
    """Fragmento HTML: texto de cima, lâmina e texto de baixo."""
    partes = [_paragrafos(email.texto_inicio)]
    if src_imagem and email.imagem:
        dim = dimensoes_imagem(email.imagem)
        largura = min(dim[0], largura_max) if dim else largura_max
        altura = f' height="{round(dim[1] * largura / dim[0])}"' if dim and dim[0] else ""
        partes.append(
            f'<p style="margin:0 0 12px 0"><img src="{html.escape(src_imagem)}" '
            f'width="{largura}"{altura} alt="" style="display:block;border:0"></p>\n'
        )
    partes.append(_paragrafos(email.texto_fim))
    return "".join(partes)


def documento_html(fragmento: str) -> str:
    return f'<html><head><meta charset="utf-8"></head><body>\n{fragmento}</body></html>'


def inserir_no_inicio_do_body(html_base: str, fragmento: str) -> str:
    """Coloca o conteúdo antes da assinatura que o Outlook já pôs no corpo."""
    m = re.search(r"<body[^>]*>", html_base, flags=re.IGNORECASE)
    if not m:
        return documento_html(fragmento) if not html_base.strip() else fragmento + html_base
    return html_base[:m.end()] + "\n" + fragmento + html_base[m.end():]
