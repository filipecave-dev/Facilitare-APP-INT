"""Importação dos dados do Disparo de Lâminas (Windows) para o Mac.

No Windows os dados ficam em ``%APPDATA%\\Disparo de Laminas`` (cole esse
endereço no Explorer). Copie essa pasta para o Mac (pendrive, OneDrive,
e-mail...) e use Configurações › "Importar dados do Windows...".

- **Histórico de enviados**: mesclado ao do Mac — o controle de quem já
  recebeu continua valendo e nada do Mac é apagado.
- **Configurações**: traz limite, intervalo, cópias, textos, campanhas salvas
  e dados do remetente SMTP. Não traz caminhos de pastas (são do Windows) nem
  a senha do SMTP (protegida pelo Windows): informe-os de novo no Mac.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config as cfgmod
from .historico import Historico

# Campos do config.json do Windows que valem no Mac.
_CAMPOS_COPIADOS = (
    "limite_diario", "intervalo_minutos", "email_copia", "copia_oculta", "largura_imagem_px",
    "alternar_laminas", "aba_padrao", "anexos_por_campanha", "subdominio_envio",
    "remetente_email", "remetente_nome", "responder_para", "smtp_host", "smtp_porta",
    "smtp_seguranca", "smtp_usuario", "assinatura_smtp",
)


def localizar(origem: Path) -> tuple[Path | None, Path | None]:
    """Acha ``historico_envios.db`` e ``config.json`` na pasta escolhida (ou
    numa subpasta "Disparo de Laminas" dentro dela)."""
    origem = Path(origem)
    if origem.is_file():
        origem = origem.parent
    for pasta in (origem, origem / "Disparo de Laminas"):
        historico, config = pasta / "historico_envios.db", pasta / "config.json"
        if historico.is_file() or config.is_file():
            return (historico if historico.is_file() else None,
                    config if config.is_file() else None)
    return None, None


def importar(origem: Path, cfg: dict, historico: Historico) -> list[str]:
    """Importa para ``cfg`` (não salva) e ``historico``. Devolve o resumo."""
    arquivo_historico, arquivo_config = localizar(origem)
    if not arquivo_historico and not arquivo_config:
        raise FileNotFoundError(
            "Não achei historico_envios.db nem config.json nessa pasta. Escolha a pasta "
            "'Disparo de Laminas' copiada do Windows (%APPDATA%\\Disparo de Laminas).")
    resumo = []
    if arquivo_historico:
        trazidos, repetidos = historico.mesclar(arquivo_historico)
        resumo.append(f"Histórico: {trazidos} registro(s) trazido(s)"
                      + (f", {repetidos} já existiam" if repetidos else "") + ".")
    if arquivo_config:
        windows = json.loads(arquivo_config.read_text(encoding="utf-8"))
        copiados = [c for c in _CAMPOS_COPIADOS if windows.get(c) not in (None, "")]
        for campo in copiados:
            cfg[campo] = windows[campo]
        mensagens = windows.get("mensagens") or {}
        cfg.setdefault("mensagens", {}).update(mensagens)
        novas = {nome: dados for nome, dados in (windows.get("campanhas_salvas") or {}).items()
                 if nome not in (cfg.get("campanhas_salvas") or {})}
        cfg.setdefault("campanhas_salvas", {}).update(novas)
        if windows.get("smtp_host"):
            cfg["provedor_smtp"] = next((k for k, p in cfgmod.PROVEDORES_SMTP.items()
                                         if p["host"] == windows["smtp_host"]), "outro")
        resumo.append(f"Configurações: {len(copiados)} campo(s), {len(mensagens)} texto(s) e "
                      f"{len(novas)} campanha(s) salva(s).")
        if windows.get("smtp_senha"):
            resumo.append("A senha do SMTP não vem do Windows: informe-a em Configurações.")
        resumo.append("Confira a pasta das lâminas em Configurações (os caminhos do Windows "
                      "não valem no Mac); as campanhas salvas acham as lâminas pelo nome do arquivo.")
    return resumo
