"""Testes offline do coletor de conteúdo (RSS/HTML)."""

from __future__ import annotations

from datetime import datetime, timezone

from informativo.coleta import _candidatos_feed, _parse_data, _parse_feed, _strip_html


def test_parse_data_rss_e_atom():
    d1 = _parse_data("Mon, 15 Sep 2026 11:11:00 -0300")
    assert d1 is not None and d1.tzinfo is not None
    d2 = _parse_data("2026-09-15T10:00:00Z")
    assert d2 is not None and d2.year == 2026
    assert _parse_data("data inválida") is None
    assert _parse_data("") is None


def test_strip_html_remove_tags_e_scripts():
    html = "<div>Olá <b>mundo</b><script>ignore()</script> fim</div>"
    assert _strip_html(html) == "Olá mundo fim"


def test_parse_feed_rss():
    xml = (
        "<?xml version='1.0'?><rss version='2.0'><channel>"
        "<item><title>Greve na Italia</title>"
        "<description>Voos afetados</description>"
        "<pubDate>Mon, 15 Sep 2026</pubDate></item>"
        "<item><title>Aeroporto reabre</title>"
        "<description>Normal</description></item>"
        "</channel></rss>"
    ).encode("utf-8")
    itens = _parse_feed(xml)
    assert len(itens) == 2
    assert itens[0][1] == "Greve na Italia"
    assert itens[0][0] == "Mon, 15 Sep 2026"


def test_parse_feed_atom():
    xml = (
        "<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry><title>Cancelamentos</title><summary>Resumo</summary>"
        "<updated>2026-09-15</updated></entry></feed>"
    ).encode("utf-8")
    itens = _parse_feed(xml)
    assert itens and itens[0][1] == "Cancelamentos"


def test_parse_feed_invalido_retorna_vazio():
    assert _parse_feed(b"nao e xml") == []


def test_candidatos_inclui_feed_e_rss():
    cands = _candidatos_feed("https://exemplo.com")
    assert "https://exemplo.com/feed" in cands
    assert "https://exemplo.com/rss" in cands
