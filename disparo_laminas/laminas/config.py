"""Configurações editáveis do disparo, gravadas em ``config.json``.

Tudo o que muda de um disparo para outro fica aqui (e na aba Configurações /
Mensagem do programa): pasta das lâminas, limite diário, intervalo, cópia,
conta do Outlook e os textos de cada campanha.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

PASTA_PROGRAMA = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG = PASTA_PROGRAMA / "config.json"

# Chave usada para a mensagem que vale para campanhas sem texto próprio.
MENSAGEM_PADRAO = "padrao"

DEFAULTS: dict = {
    # Pasta raiz das lâminas: cada subpasta é uma campanha (corporativo,
    # eventos, incentivo...) com as imagens daquela campanha.
    "pasta_laminas": str(
        Path.home() / "OneDrive - Veronezzi Serviços Comerciais LTDA" / "DOCUMENTOS"
        / "TIVOLITUR" / "LAMINAS PROSPECT"
    ),
    "limite_diario": 80,
    "intervalo_minutos": 3.0,
    # E-mail que recebe cópia (CC) nos contatos marcados antes do disparo.
    "email_copia": "",
    # Cópia oculta (CCO) em todos os envios, se preenchida.
    "copia_oculta": "",
    # Conta do Outlook usada no envio (em branco = conta padrão).
    "conta_outlook": "",
    # Mantém a assinatura padrão do Outlook no fim do e-mail.
    "incluir_assinatura": True,
    # Largura máxima da lâmina no corpo do e-mail, em pixels.
    "largura_imagem_px": 560,
    # Alterna entre as lâminas da campanha a cada envio (rodízio).
    "alternar_laminas": False,
    # Simulação: gera os e-mails em arquivos HTML em vez de enviar.
    "modo_simulacao": False,
    "aba_padrao": "A ENVIAR",
    "ultima_base": "",
    "ultima_campanha": "",
    "mensagens": {
        MENSAGEM_PADRAO: {
            "assunto": "CONFIRMANDO REUNIÃO com {nome} da {empresa} - Viagens Corporativas",
            "texto_inicio": (
                "Olá {nome}, {saudacao}!\n"
                "Tudo bem com você?\n\n"
                "Queremos ser seu parceiro na gestão das viagens da sua empresa.\n\n"
                "Podemos agendar uma chamada de vídeo na plataforma Teams?"
            ),
            "texto_fim": "Agradeço desde já e fico no seu aguardo.\n\nAtenciosamente,",
        },
    },
}


def carregar(caminho: os.PathLike | str = ARQUIVO_CONFIG) -> dict:
    """Lê o ``config.json``; campos ausentes recebem o valor padrão."""
    cfg = copy.deepcopy(DEFAULTS)
    caminho = Path(caminho)
    if caminho.exists():
        with caminho.open(encoding="utf-8") as f:
            salvo = json.load(f)
        mensagens = salvo.pop("mensagens", None) or {}
        cfg.update(salvo)
        cfg["mensagens"].update(mensagens)
    return cfg


def salvar(cfg: dict, caminho: os.PathLike | str = ARQUIVO_CONFIG) -> None:
    caminho = Path(caminho)
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def mensagem_da_campanha(cfg: dict, campanha: str) -> dict:
    """Mensagem (assunto/textos) da campanha, ou a padrão se ela não tiver."""
    mensagens = cfg.get("mensagens") or {}
    padrao = mensagens.get(MENSAGEM_PADRAO) or DEFAULTS["mensagens"][MENSAGEM_PADRAO]
    propria = mensagens.get(campanha) if campanha else None
    return dict(propria or padrao)


def tem_mensagem_propria(cfg: dict, campanha: str) -> bool:
    return bool(campanha) and campanha in (cfg.get("mensagens") or {})
