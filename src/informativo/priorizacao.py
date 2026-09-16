"""Priorização e deduplicação das notícias captadas.

Duas inteligências, sem custo extra de API:

* **Prioridade** — pontua cada notícia por tema, para que **desastres
  naturais**, **greves em aeroportos/companhias aéreas** e **fatos no Brasil
  que afetem a aviação e as viagens** apareçam primeiro.
* **Deduplicação** — gera uma assinatura textual normalizada e compara por
  similaridade (Jaccard) para não trazer o mesmo conteúdo repetido.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Pesos por tema, em faixas (tiers) para garantir a ordem pedida:
# 1) desastres naturais  2) greves em aeroportos/cias aéreas
# 3) aviação/viagens (Brasil primeiro). As bases são espaçadas para que uma
# faixa superior sempre fique acima da soma das inferiores.
PESO_DESASTRE = 1000
PESO_GREVE_AVIACAO = 500
PESO_AVIACAO_VIAGEM = 200
PESO_BRASIL = 50  # bônus quando o fato é no Brasil

_DESASTRES = (
    "desastre natural", "terremoto", "sismo", "tsunami", "furacao", "furacão",
    "ciclone", "tornado", "tempestade", "temporal", "enchente", "inundacao",
    "inundação", "alagamento", "deslizamento", "vulcao", "vulcão", "erupcao",
    "erupção", "seca", "onda de calor", "nevasca", "vendaval", "granizo",
    "incendio florestal", "incêndio florestal", "queimada",
)
_GREVE = ("greve", "paralisacao", "paralisação", "protesto", "manifestacao",
          "manifestação", "sindicato", "walkout", "strike")
_AVIACAO = (
    "aeroporto", "aeroportos", "voo", "voos", "aviacao", "aviação", "aérea",
    "aerea", "companhia aerea", "companhia aérea", "cia aerea", "cia aérea",
    "anac", "infraero", "controladores de voo", "espaco aereo", "espaço aéreo",
    "gru", "guarulhos", "congonhas", "galeao", "galeão", "aeronave",
    "cancelamento de voo", "atraso de voo", "fechamento de aeroporto",
    "pista", "decolagem", "pouso",
)
_VIAGEM = ("viagem", "viagens", "viajante", "turismo", "rodovia", "estrada",
           "porto", "ferrovia", "trem", "metro", "metrô", "transporte")
_BRASIL = ("brasil", "brasileiro", "brasileira", "são paulo", "sao paulo",
           "rio de janeiro", "brasília", "brasilia", "belo horizonte",
           "recife", "salvador", "fortaleza", "curitiba", "porto alegre")


def _sem_acentos(txt: str) -> str:
    norm = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in norm if not unicodedata.combining(c))


def _tem(txt: str, termos) -> bool:
    return any(t in txt for t in termos)


def prioridade_da_noticia(texto: str, regiao: str = "") -> int:
    """Pontua a notícia por tema (0 = sem destaque; maior = mais no topo)."""
    base = (texto or "") + " " + (regiao or "")
    t = _sem_acentos(base.lower())
    # acentos removidos: normaliza também as listas na comparação
    def _hit(termos):
        return _tem(t, [_sem_acentos(x) for x in termos])

    score = 0
    aviacao = _hit(_AVIACAO)
    if _hit(_DESASTRES):
        score += PESO_DESASTRE
    if _hit(_GREVE) and aviacao:
        score += PESO_GREVE_AVIACAO
    if aviacao or _hit(_VIAGEM):
        score += PESO_AVIACAO_VIAGEM
    if _hit(_BRASIL) or "brasil" in _sem_acentos((regiao or "").lower()):
        score += PESO_BRASIL
    return score


# -- deduplicação -----------------------------------------------------------
def _tokens(texto: str) -> set[str]:
    t = _sem_acentos((texto or "").lower())
    return {p for p in re.findall(r"[a-z0-9]{4,}", t)}


def assinatura(texto: str) -> str:
    """Hash estável do conteúdo normalizado (para detectar repetição exata)."""
    t = _sem_acentos((texto or "").lower())
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def similaridade(a: str, b: str) -> float:
    """Similaridade de Jaccard entre dois textos (0..1)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    uniao = len(ta | tb)
    return inter / uniao if uniao else 0.0


def e_repetida(texto: str, existentes, *, limiar: float = 0.8) -> bool:
    """True se ``texto`` repete algum dos ``existentes`` (por assinatura ou
    similaridade acima do ``limiar``)."""
    assn = assinatura(texto)
    for ex in existentes:
        ex_txt = ex if isinstance(ex, str) else (ex.get("conteudo") or "")
        ex_assn = ex.get("assinatura") if isinstance(ex, dict) else None
        if ex_assn and ex_assn == assn:
            return True
        if similaridade(texto, ex_txt) >= limiar:
            return True
    return False
