"""Paletas de tema do Informativo.

A tela de Configurações permite trocar a cor de destaque (accent) do sistema,
no mesmo espírito do QuitaCalc. O padrão é **azul** (``#2557d6``). Cada tema é
apenas uma cor primária; as variáveis CSS derivadas (tinta do texto sobre o
primário e o fundo/tinta dos *badges*) são calculadas a partir dela.
"""

from __future__ import annotations

from dataclasses import dataclass

# Chave persistida em ``configuracoes`` para a cor de tema selecionada.
CHAVE_TEMA = "tema_primary"

# Cor padrão: azul (idêntico ao primário do QuitaCalc).
TEMA_PADRAO = "#2557d6"


@dataclass(frozen=True)
class TemaPreset:
    """Um preset de tema exibido como amostra clicável nas Configurações."""

    id: str
    rotulo: str
    primary: str


# Presets oferecidos na tela de Configurações. O primeiro é o padrão (azul).
PRESETS: tuple[TemaPreset, ...] = (
    TemaPreset("azul", "Azul (padrão)", "#2557d6"),
    TemaPreset("indigo", "Índigo", "#4f46e5"),
    TemaPreset("teal", "Turquesa", "#0d9488"),
    TemaPreset("verde", "Verde", "#1c7a43"),
    TemaPreset("ambar", "Âmbar", "#b45309"),
    TemaPreset("vermelho", "Vermelho", "#c0362c"),
    TemaPreset("roxo", "Roxo", "#7c3aed"),
    TemaPreset("grafite", "Grafite", "#334155"),
)


def _hex_valido(cor: str) -> bool:
    if not isinstance(cor, str):
        return False
    cor = cor.strip()
    if not cor.startswith("#") or len(cor) != 7:
        return False
    try:
        int(cor[1:], 16)
    except ValueError:
        return False
    return True


def normalizar_cor(cor: str) -> str:
    """Valida a cor primária; devolve o padrão azul se for inválida."""
    cor = (cor or "").strip().lower()
    return cor if _hex_valido(cor) else TEMA_PADRAO


def _luminancia(cor: str) -> float:
    r = int(cor[1:3], 16) / 255
    g = int(cor[3:5], 16) / 255
    b = int(cor[5:7], 16) / 255
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def tinta_de_contraste(cor: str) -> str:
    """Escolhe texto branco ou escuro conforme a luminância do fundo."""
    return "#ffffff" if _luminancia(cor) < 0.6 else "#1c2431"


def _mistura(cor: str, alvo: str, fator: float) -> str:
    """Interpola ``cor`` em direção a ``alvo`` (0..1) — usado para tons claros."""
    def canal(a: str, b: str) -> int:
        va, vb = int(a, 16), int(b, 16)
        return round(va + (vb - va) * fator)

    return "#{:02x}{:02x}{:02x}".format(
        canal(cor[1:3], alvo[1:3]),
        canal(cor[3:5], alvo[3:5]),
        canal(cor[5:7], alvo[5:7]),
    )


def variaveis_css(cor_primary: str) -> dict[str, str]:
    """Deriva o conjunto de variáveis CSS de tema a partir da cor primária."""
    primary = normalizar_cor(cor_primary)
    return {
        "--primary": primary,
        "--primary-ink": tinta_de_contraste(primary),
        "--badge-bg": _mistura(primary, "#ffffff", 0.88),
        "--badge-ink": primary,
    }
