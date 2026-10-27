"""Repositório de lâminas: cada subpasta da pasta raiz é uma campanha.

Exemplo::

    LAMINAS PROSPECT/
    ├── CORPORATIVO/   Tivolitur-0426.jpeg, Tivolitur-0526.jpeg
    ├── EVENTOS/       ...
    └── INCENTIVO/     ...

Imagens soltas na raiz aparecem na campanha "(geral)".
"""

from __future__ import annotations

from pathlib import Path

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".gif"}
CAMPANHA_GERAL = "(geral)"


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
        (p.name for p in raiz.iterdir() if p.is_dir() and _imagens(p)),
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
