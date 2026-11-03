"""Repositório de lâminas: cada subpasta da pasta raiz é uma campanha.

Exemplo::

    LAMINAS PROSPECT/
    ├── CORPORATIVO/   Tivolitur-0426.jpeg, Tivolitur-0526.jpeg
    ├── EVENTOS/       ...
    └── INCENTIVO/     ...

Imagens soltas na raiz aparecem na campanha "(geral)".

A subpasta **APRESENTAÇÃO** não é campanha: guarda as apresentações (PDF,
PowerPoint...) enviadas como anexo — a de cada campanha é escolhida pelo nome
do arquivo (ex.: "institucional" para Corporativo, "eventos" para Eventos) ou
manualmente na tela.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Optional

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".gif"}
EXTENSOES_ANEXO = {".pdf", ".pptx", ".ppt", ".ppsx", ".pps", ".docx", ".doc", ".xlsx", ".zip"}
CAMPANHA_GERAL = "(geral)"
PASTA_APRESENTACOES = "APRESENTAÇÃO"
# Palavras do nome do arquivo que indicam a apresentação de cada campanha.
_PALAVRAS_ANEXO = {
    "corporativo": ("institucional", "corporativ"),
    "eventos": ("evento",),
    "incentivo": ("incentivo",),
}


def _norm(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c)).casefold()


def _eh_pasta_de_apresentacoes(pasta: Path) -> bool:
    return _norm(pasta.name).startswith("apresenta")


def _imagens(pasta: Path) -> list[Path]:
    arquivos = [p for p in pasta.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSOES_IMAGEM]
    # Mais recente primeiro: normalmente é a lâmina do mês.
    return sorted(arquivos, key=lambda p: p.stat().st_mtime, reverse=True)


def listar_campanhas(pasta_raiz: str) -> list[str]:
    """Nomes das campanhas (subpastas que contêm imagens)."""
    raiz = Path(pasta_raiz) if pasta_raiz else None
    if raiz is None or not raiz.is_dir():
        return []
    campanhas = sorted(
        (p.name for p in raiz.iterdir()
         if p.is_dir() and not _eh_pasta_de_apresentacoes(p) and _imagens(p)),
        key=str.casefold,
    )
    if _imagens(raiz):
        campanhas.append(CAMPANHA_GERAL)
    return campanhas


def listar_laminas(pasta_raiz: str, campanha: str) -> list[Path]:
    """Imagens da campanha, da mais recente para a mais antiga."""
    if not pasta_raiz or not campanha:
        return []
    raiz = Path(pasta_raiz)
    pasta = raiz if campanha == CAMPANHA_GERAL else raiz / campanha
    return _imagens(pasta) if pasta.is_dir() else []


def lamina_do_envio(laminas: list[Path], indice: int, alternar: bool) -> Path | None:
    """Lâmina usada no ``indice``-ésimo envio: a primeira da lista ou, com
    ``alternar``, uma de cada vez em rodízio (mescla as lâminas da campanha)."""
    if not laminas:
        return None
    return laminas[indice % len(laminas)] if alternar else laminas[0]


def pasta_apresentacoes(pasta_raiz: str, pasta_configurada: str = "") -> Optional[Path]:
    """Pasta das apresentações: a configurada ou ``<raiz>/APRESENTAÇÃO``
    (aceita variações de acento/maiúsculas, ex.: "Apresentacoes")."""
    if pasta_configurada:
        return Path(pasta_configurada)
    if not pasta_raiz or not Path(pasta_raiz).is_dir():
        return None
    for p in Path(pasta_raiz).iterdir():
        if p.is_dir() and _eh_pasta_de_apresentacoes(p):
            return p
    return Path(pasta_raiz) / PASTA_APRESENTACOES


def listar_anexos(pasta: Optional[Path]) -> list[Path]:
    if pasta is None or not pasta.is_dir():
        return []
    arquivos = [p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSOES_ANEXO
                and not p.name.startswith("~$")]  # ignora temporários do Office
    return sorted(arquivos, key=lambda p: p.name.casefold())


def sugerir_anexo(anexos: list[Path], campanha: str) -> Optional[Path]:
    """Apresentação que combina com a campanha pelo nome do arquivo."""
    chave = _norm(campanha or "")
    palavras = _PALAVRAS_ANEXO.get(chave, ()) + ((chave.rstrip("s"),) if chave else ())
    for palavra in palavras:
        for p in anexos:
            if palavra and palavra in _norm(p.stem):
                return p
    return None
