"""Configurações editáveis do disparo, gravadas em ``config.json``.

Tudo o que muda de um disparo para outro fica aqui (e na aba Configurações /
Mensagem do programa): pasta das lâminas, limite diário, intervalo, cópia,
conta do Outlook e os textos de cada campanha.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Optional

PASTA_PROGRAMA = Path(__file__).resolve().parent.parent


def _pasta_dados() -> Path:
    """Pasta dos dados do usuário (configurações, histórico, simulações).

    Fica FORA da pasta do programa — em ``%APPDATA%\\Disparo de Laminas`` no
    Windows — para que a pasta do programa possa ser apagada e substituída a
    cada versão sem perder o controle de enviados.
    """
    if os.environ.get("DISPARO_LAMINAS_DADOS"):
        return Path(os.environ["DISPARO_LAMINAS_DADOS"])
    if os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "Disparo de Laminas"
    return Path.home() / ".disparo_laminas"


PASTA_DADOS = _pasta_dados()
ARQUIVO_CONFIG = PASTA_DADOS / "config.json"
ARQUIVO_HISTORICO = PASTA_DADOS / "historico_envios.db"
PASTA_SIMULACAO = PASTA_DADOS / "simulacao"
PASTA_BACKUPS = PASTA_DADOS / "backups"
MAX_BACKUPS = 30

# Formas de envio. As de Outlook usam o Outlook instalado; a SMTP fala direto
# com o servidor de e-mail do subdomínio de prospecção.
MODOS_ENVIO = {
    "outlook": "Outlook — conta padrão",
    "outlook_conta": "Outlook — conta do subdomínio cadastrada no Outlook",
    "outlook_enviar_como": "Outlook — enviar como (De:) o endereço do subdomínio",
    "smtp": "SMTP direto — servidor de e-mail do subdomínio",
}
SEGURANCAS_SMTP = {"starttls": "STARTTLS (porta 587)", "ssl": "SSL/TLS (porta 465)",
                   "nenhuma": "Sem criptografia (porta 25)"}

# Chave usada para a mensagem que vale para campanhas sem texto próprio.
MENSAGEM_PADRAO = "padrao"

DEFAULTS: dict = {
    # Pasta raiz das lâminas: cada subpasta é uma campanha (corporativo,
    # eventos, incentivo...) com as imagens daquela campanha.
    "pasta_laminas": str(
        Path.home() / "OneDrive - Veronezzi Serviços Comerciais LTDA" / "DOCUMENTOS"
        / "TIVOLITUR" / "LAMINAS PROSPECT"
    ),
    # Pasta das apresentações enviadas como anexo (em branco = subpasta
    # APRESENTAÇÃO dentro da pasta das lâminas).
    "pasta_anexos": "",
    # Campanha -> nome do arquivo de apresentação ("" = sem anexo). Campanha
    # fora daqui usa o arquivo cujo nome combina (institucional, eventos...).
    "anexos_por_campanha": {},
    # Quantidade máxima de e-mails por dia e minutos entre um e outro.
    "limite_diario": 80,
    "intervalo_minutos": 3.0,
    # E-mail que recebe cópia (CC) nos contatos marcados antes do disparo.
    "email_copia": "",
    # Cópia oculta (CCO) em todos os envios, se preenchida.
    "copia_oculta": "",
    # Remetente das prospecções (ver MODOS_ENVIO). O subdomínio (ex.:
    # prospeccao.suaempresa.com.br) protege a reputação do domínio principal.
    "modo_envio": "outlook",
    "subdominio_envio": "",
    "remetente_email": "",
    "remetente_nome": "",
    # Para onde vão as respostas (Reply-To), ex.: o e-mail do domínio principal.
    "responder_para": "",
    "smtp_host": "",
    "smtp_porta": 587,
    "smtp_seguranca": "starttls",
    "smtp_usuario": "",
    "smtp_senha": "",  # protegida (ver segredo.py)
    # No SMTP não há assinatura do Outlook: este texto entra no fim do e-mail.
    "assinatura_smtp": "",
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
        # Até a 1.6: só havia "conta_outlook" (conta do Outlook que envia).
        if "modo_envio" not in salvo and salvo.get("conta_outlook"):
            salvo["modo_envio"] = "outlook_conta"
            salvo.setdefault("remetente_email", salvo["conta_outlook"])
        cfg.update(salvo)
        cfg["mensagens"].update(mensagens)
    if cfg.get("modo_envio") not in MODOS_ENVIO:
        cfg["modo_envio"] = "outlook"
    return cfg


def salvar(cfg: dict, caminho: os.PathLike | str = ARQUIVO_CONFIG) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
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


def migrar_dados_antigos(pasta_programa: Path = PASTA_PROGRAMA,
                         pasta_dados: Path = PASTA_DADOS) -> list[str]:
    """Traz para a pasta de dados o ``config.json`` e o histórico que as
    versões até 1.5.x gravavam dentro da pasta do programa. Nunca sobrescreve
    o que já existe na pasta de dados. Retorna o que foi copiado."""
    copiados = []
    origens = (
        (pasta_programa / "config.json", pasta_dados / "config.json"),
        (pasta_programa / "dados" / "historico_envios.db", pasta_dados / "historico_envios.db"),
    )
    for origem, destino in origens:
        if origem.is_file() and not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino)
            copiados.append(destino.name)
    return copiados


def dominio_do_email(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in (email or "") else ""


def normalizar_subdominio(valor: str) -> str:
    valor = (valor or "").strip().lower()
    for prefixo in ("https://", "http://", "www.", "@"):
        if valor.startswith(prefixo):
            valor = valor[len(prefixo):]
    return valor.strip("/ .")


def avisos_remetente(cfg: dict) -> list[str]:
    """Inconsistências entre o subdomínio configurado e o remetente."""
    avisos = []
    sub = normalizar_subdominio(cfg.get("subdominio_envio", ""))
    modo = cfg.get("modo_envio", "outlook")
    remetente = (cfg.get("remetente_email") or "").strip()
    if modo != "outlook" and not remetente:
        avisos.append("Informe o e-mail remetente do subdomínio.")
    if sub and modo == "outlook":
        avisos.append(f"Há subdomínio ({sub}), mas a forma de envio é a conta padrão do "
                      "Outlook: os e-mails NÃO sairão pelo subdomínio.")
    if sub and remetente and dominio_do_email(remetente) != sub:
        avisos.append(f"O remetente {remetente} não é do subdomínio {sub}.")
    if modo == "smtp":
        faltando = [rotulo for chave, rotulo in (("smtp_host", "servidor"), ("smtp_usuario", "usuário"),
                                                  ("smtp_senha", "senha")) if not cfg.get(chave)]
        if faltando:
            avisos.append("Envio SMTP sem " + ", ".join(faltando) + ".")
    return avisos


def descricao_remetente(cfg: dict) -> str:
    """Texto curto do remetente em uso (tela, resumo e histórico)."""
    modo = cfg.get("modo_envio", "outlook")
    remetente = (cfg.get("remetente_email") or "").strip()
    if modo == "outlook" or not remetente:
        return "Outlook (conta padrão)"
    sufixo = {"outlook_conta": "Outlook, conta", "outlook_enviar_como": "Outlook, enviar como",
              "smtp": "SMTP"}[modo]
    return f"{remetente} ({sufixo})"


def backup_dados(versao: str, pasta_dados: Path = PASTA_DADOS,
                 agora: Optional[datetime] = None) -> Optional[Path]:
    """Cópia de segurança do histórico e do config.json ao abrir o programa:
    uma por dia e sempre que a versão muda. Mantém as ``MAX_BACKUPS`` mais
    recentes em ``backups/``. Retorna a pasta criada (ou ``None``)."""
    agora = agora or datetime.now()
    historico = pasta_dados / "historico_envios.db"
    config = pasta_dados / "config.json"
    if not historico.exists() and not config.exists():
        return None
    pasta = pasta_dados / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    marca = pasta / "ultimo_backup.txt"
    chave = f"{agora:%Y-%m-%d}|{versao}"
    if marca.exists() and marca.read_text(encoding="utf-8").strip() == chave:
        return None
    destino = pasta / f"{agora:%Y%m%d_%H%M%S}_v{versao}"
    destino.mkdir(parents=True, exist_ok=True)
    if historico.exists():
        # API de backup do SQLite: cópia consistente mesmo com o banco aberto.
        with closing(sqlite3.connect(historico)) as origem, \
                closing(sqlite3.connect(destino / historico.name)) as copia:
            origem.backup(copia)
    if config.exists():
        shutil.copy2(config, destino / config.name)
    marca.write_text(chave, encoding="utf-8")
    antigos = sorted((p for p in pasta.iterdir() if p.is_dir()), key=lambda p: p.name)
    for velho in antigos[:-MAX_BACKUPS]:
        shutil.rmtree(velho, ignore_errors=True)
    return destino
