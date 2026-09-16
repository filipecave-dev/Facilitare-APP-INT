"""Coleta de conteúdo recente das fontes (RSS/Atom ou HTML).

Para que a IA resuma **fatos atuais** — e não do conhecimento geral dela — o
sistema baixa o conteúdo recente da fonte e o entrega no prompt. Tenta primeiro
um **feed RSS/Atom** (títulos + descrições das últimas publicações) e, se não
houver, cai para o **texto da página**. Usa apenas a biblioteca padrão.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

_UA = "Mozilla/5.0 (InformaTivo/1.0; +https://centralinformativo.onrender.com)"
_MAX_BYTES = 600_000


def _baixar(url: str, timeout: int) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        return r.read(_MAX_BYTES), ctype


class _ExtratorTexto(HTMLParser):
    def __init__(self):
        super().__init__()
        self._partes: list[str] = []
        self._pular = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._pular += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._pular > 0:
            self._pular -= 1

    def handle_data(self, data):
        if self._pular == 0:
            s = data.strip()
            if s:
                self._partes.append(s)

    def texto(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._partes)).strip()


def _strip_html(txt: str) -> str:
    ext = _ExtratorTexto()
    try:
        ext.feed(txt or "")
    except Exception:  # noqa: BLE001
        return re.sub(r"<[^>]+>", " ", txt or "")
    return ext.texto()


def _tag(el) -> str:
    return el.tag.split("}")[-1].lower()


def _parse_data(txt: str):
    """Interpreta datas de RSS (RFC822) e Atom (ISO). Retorna datetime aware ou None."""
    if not txt:
        return None
    txt = txt.strip()
    try:
        d = parsedate_to_datetime(txt)
        if d is not None:
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_feed(xml_bytes: bytes, max_itens: int = 10) -> list[tuple[str, str, str]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    itens: list[tuple[str, str, str]] = []
    for el in root.iter():
        if _tag(el) in ("item", "entry"):
            titulo = desc = data = ""
            for c in el:
                tg = _tag(c)
                if tg == "title":
                    titulo = (c.text or "").strip()
                elif tg in ("description", "summary", "content") and not desc:
                    desc = (c.text or "").strip()
                elif tg in ("pubdate", "updated", "published", "date") and not data:
                    data = (c.text or "").strip()
            if titulo or desc:
                itens.append((data, titulo, desc))
            if len(itens) >= max_itens:
                break
    return itens


def _candidatos_feed(url: str) -> list[str]:
    base = url.rstrip("/")
    return [
        url,
        base + "/feed",
        base + "/rss",
        base + "/feed/",
        base + "/rss.xml",
        base + "/index.xml",
        base + "/atom.xml",
    ]


def coletar_conteudo(url: str, *, feed_url: str = "", timeout: int = 12,
                     max_chars: int = 2200, dias: int = 0) -> str:
    """Devolve um trecho com o conteúdo recente da fonte, ou '' se não obtiver.

    Se ``feed_url`` (RSS cadastrado) for informado, ele é tentado primeiro —
    mais preciso e econômico. Se ``dias > 0``, mantém apenas itens publicados
    nos últimos ``dias`` dias (itens sem data são preservados), o que foca a
    captação em notícias recentes e reduz o texto enviado à IA (menos tokens).
    """
    if not url and not feed_url:
        return ""
    limite = None
    if dias and dias > 0:
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
    # 1) Tenta o RSS cadastrado primeiro, depois candidatos derivados da URL.
    candidatos = ([feed_url] if feed_url else []) + (_candidatos_feed(url) if url else [])
    vistos = set()
    for cand in candidatos:
        if cand in vistos:
            continue
        vistos.add(cand)
        try:
            data, ctype = _baixar(cand, timeout)
        except Exception:  # noqa: BLE001
            continue
        cabeca = data[:300].lower()
        parece_feed = (
            "xml" in ctype.lower()
            or cand.endswith((".xml",))
            or b"<rss" in cabeca or b"<feed" in cabeca or b"<?xml" in cabeca
        )
        if not parece_feed:
            continue
        itens = _parse_feed(data)
        if itens:
            linhas = []
            for d, t, ds in itens:
                if limite is not None:
                    dt = _parse_data(d)
                    if dt is not None and dt < limite:
                        continue  # item mais antigo que a janela
                resumo = _strip_html(ds)[:150]
                marca = f" ({d})" if d else ""
                linhas.append(f"- {t}{marca}. {resumo}".strip())
            if linhas:
                cab = "Últimas publicações da fonte"
                if dias:
                    cab += f" (últimos {dias} dias)"
                return (cab + ":\n" + "\n".join(linhas[:8]))[:max_chars]
    # 2) Fallback: texto da própria página.
    try:
        data, _ = _baixar(url, timeout)
        txt = _strip_html(data.decode("utf-8", "ignore"))
        return txt[:max_chars] if txt else ""
    except Exception:  # noqa: BLE001
        return ""
