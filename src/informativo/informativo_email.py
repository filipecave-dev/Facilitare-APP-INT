"""Geração do **e-mail final** do informativo (HTML autocontido).

A partir dos itens aprovados (já parafraseados pela IA) e das preferências da
empresa — ``nome_solucao``, ``assunto_email``, cor de destaque, modelo de fonte
e template de fundo — monta um HTML pronto para envio.

O HTML é **autocontido**: o template de fundo (quando é imagem) é embutido como
``data:`` URI, de modo que o arquivo baixado abre igual em qualquer cliente de
e-mail, sem depender do servidor. Usa tabelas e estilos inline, no padrão
compatível com clientes de e-mail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Optional

from .empresas import familia_do_modelo
from .omniroute import CaptacaoRepository


def _fundo_data_uri(template) -> str:
    """Converte ``(nome, mime, bytes)`` de imagem em ``data:`` URI, ou ''."""
    if not template:
        return ""
    _, mime, dados = template
    if not (mime or "").startswith("image/"):
        return ""
    import base64

    b64 = base64.b64encode(dados).decode("ascii")
    return f"data:{mime};base64,{b64}"


def montar_email_html(
    empresa,
    grupos: dict,
    *,
    template=None,
    logo=None,
    data: Optional[str] = None,
) -> str:
    """Monta o HTML completo do e-mail do informativo.

    * ``empresa`` — objeto :class:`~informativo.empresas.Empresa` (ou ``None``).
    * ``grupos`` — dict ``{frente: [captacoes]}`` (ordem das frentes preservada).
    * ``template`` — ``(nome, mime, bytes)`` do template de fundo, ou ``None``.
    * ``data`` — data exibida no cabeçalho (padrão: hoje, UTC).
    """
    cor = (getattr(empresa, "tema_primary", None) or "#2557d6")
    familia = familia_do_modelo(getattr(empresa, "fonte_modelo", None))
    solucao = getattr(empresa, "nome_solucao", None) or "Informativo"
    assunto = getattr(empresa, "assunto_email", None) or solucao
    if data is None:
        data = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    fundo = _fundo_data_uri(template)
    # Logo embutido (data URI) — ajustado por CSS à altura da barra.
    logo_uri = ""
    if logo:
        _, lmime, ldados = logo
        if (lmime or "").startswith("image/"):
            import base64
            logo_uri = f"data:{lmime};base64,{base64.b64encode(ldados).decode('ascii')}"
    # Logo fixo à direita da barra, proporcional ao título (altura ~2x a fonte
    # do título de 22px). Célula à direita só existe quando há logo.
    logo_html = (
        f'<img src="{logo_uri}" alt="logo" style="height:44px;max-width:200px;'
        'width:auto;display:block;object-fit:contain;">'
        if logo_uri else ""
    )
    logo_cell = (
        f'<td valign="middle" align="right" style="padding-left:16px;white-space:nowrap;">{logo_html}</td>'
        if logo_uri else ""
    )

    estilo_corpo = (
        "background-color:#eef1f6;"
        + (f"background-image:url('{fundo}');background-size:cover;"
           "background-position:center;background-attachment:fixed;" if fundo else "")
    )

    blocos = []
    tem_conteudo = False
    for frente, itens in grupos.items():
        if not itens:
            continue
        tem_conteudo = True
        linhas = []
        for c in itens:
            texto = (c.get("parafrase") or c.get("conteudo") or "").strip()
            fonte = escape(c.get("fonte_nome") or "")
            corpo_html = escape(texto).replace("\n", "<br>")
            linhas.append(
                '<tr><td style="padding:0 0 16px 0;">'
                f'<div style="font-size:15px;line-height:1.55;color:#1c2431;">{corpo_html}</div>'
                f'<div style="font-size:12px;color:#6a7686;margin-top:4px;">Fonte: {fonte}</div>'
                "</td></tr>"
            )
        blocos.append(
            f'<tr><td style="padding:6px 0 4px 0;">'
            f'<h2 style="margin:18px 0 10px;font-size:18px;color:{escape(cor)};'
            f'border-bottom:2px solid {escape(cor)};padding-bottom:6px;">{escape(frente)}</h2>'
            "</td></tr>"
            '<tr><td><table role="presentation" width="100%" cellpadding="0" '
            'cellspacing="0" border="0">' + "".join(linhas) + "</table></td></tr>"
        )
    if not tem_conteudo:
        blocos.append(
            '<tr><td style="padding:20px 0;color:#6a7686;font-size:15px;">'
            "Nenhum item aprovado para este informativo.</td></tr>"
        )

    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(assunto)}</title>
</head>
<body style="margin:0;padding:0;{estilo_corpo}font-family:{familia};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="{estilo_corpo}padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"
           style="width:640px;max-width:96%;background:#ffffff;border-radius:12px;
                  overflow:hidden;box-shadow:0 4px 18px rgba(20,30,50,.12);">
      <tr>
        <td style="background:{escape(cor)};padding:22px 28px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td valign="middle">
                <div style="color:#ffffff;font-size:22px;font-weight:700;">{escape(solucao)}</div>
                <div style="color:rgba(255,255,255,.85);font-size:13px;margin-top:2px;">
                  {escape(assunto)} &middot; {escape(data)}</div>
              </td>
              {logo_cell}
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding:20px 28px 8px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            {"".join(blocos)}
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding:16px 28px 24px;border-top:1px solid #e6ebf2;">
          <div style="font-size:12px;color:#8a94a3;">
            Enviado por {escape(solucao)}. Informativo gerado automaticamente a
            partir das fontes selecionadas.</div>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def montar_grupos(captacoes: list[dict]) -> dict:
    """Agrupa captações por frente (sem frente cai em 'Informativo')."""
    grupos = {f: [] for f in CaptacaoRepository.FRENTES}
    for c in captacoes:
        fr = c.get("frente") or "Informativo"
        grupos.setdefault(fr, []).append(c)
    return grupos
