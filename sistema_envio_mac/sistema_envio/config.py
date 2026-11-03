"""Configurações editáveis do envio, gravadas em ``config.json``.

Tudo o que muda de um disparo para outro fica aqui (e nas abas Configurações /
Mensagem do programa): pasta das lâminas, limite diário, intervalo, cópia,
remetente/SMTP do subdomínio e os textos de cada campanha.
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
NOME_APP = "Sistema de Envio"


def _pasta_dados() -> Path:
    """Pasta dos dados do usuário (configurações, histórico, simulações).

    Fica FORA da pasta do programa — em ``~/Library/Application Support/
    Sistema de Envio`` no Mac — para que a pasta do programa possa ser apagada
    e substituída a cada versão sem perder o controle de enviados.
    """
    if os.environ.get("SISTEMA_ENVIO_DADOS"):
        return Path(os.environ["SISTEMA_ENVIO_DADOS"])
    return Path.home() / "Library" / "Application Support" / NOME_APP


PASTA_DADOS = _pasta_dados()
ARQUIVO_CONFIG = PASTA_DADOS / "config.json"
ARQUIVO_HISTORICO = PASTA_DADOS / "historico_envios.db"
PASTA_SIMULACAO = PASTA_DADOS / "simulacao"
PASTA_BACKUPS = PASTA_DADOS / "backups"
MAX_BACKUPS = 30

SEGURANCAS_SMTP = {"starttls": "STARTTLS (porta 587)", "ssl": "SSL/TLS (porta 465)",
                   "nenhuma": "Sem criptografia (porta 25)"}

# Provedores comuns: preenchem servidor, porta e segurança do SMTP.
PROVEDORES_SMTP = {
    "microsoft": {"rotulo": "Microsoft 365 / Exchange Online", "host": "smtp.office365.com",
                  "porta": 587, "seguranca": "starttls",
                  "ajuda": "Usuário = e-mail completo. O administrador precisa permitir "
                           "'SMTP autenticado' nessa caixa (Centro de administração do Microsoft 365)."},
    "google": {"rotulo": "Google Workspace / Gmail", "host": "smtp.gmail.com",
               "porta": 587, "seguranca": "starttls",
               "ajuda": "Usuário = e-mail completo. Use uma 'senha de app' (exige verificação em 2 etapas)."},
    "locaweb": {"rotulo": "Locaweb", "host": "email-ssl.com.br", "porta": 465, "seguranca": "ssl",
                "ajuda": "Usuário = e-mail completo e a senha da caixa."},
    "hostinger": {"rotulo": "Hostinger", "host": "smtp.hostinger.com", "porta": 465, "seguranca": "ssl",
                  "ajuda": "Usuário = e-mail completo e a senha da caixa."},
    "zoho": {"rotulo": "Zoho Mail", "host": "smtp.zoho.com", "porta": 587, "seguranca": "starttls",
             "ajuda": "Usuário = e-mail completo. Com 2 etapas ativas, use senha de app."},
    "outro": {"rotulo": "Outro servidor (informar os dados)", "host": "", "porta": 587,
              "seguranca": "starttls",
              "ajuda": "Peça a quem administra o e-mail do subdomínio: servidor SMTP, porta e segurança."},
}

# Chave usada para a mensagem que vale para campanhas sem texto próprio.
MENSAGEM_PADRAO = "padrao"


def _pasta_laminas_padrao() -> str:
    """No Mac o OneDrive fica em ~/Library/CloudStorage/OneDrive-<Empresa>."""
    subpasta = Path("DOCUMENTOS") / "TIVOLITUR" / "LAMINAS PROSPECT"
    nuvem = Path.home() / "Library" / "CloudStorage"
    if nuvem.is_dir():
        for onedrive in sorted(nuvem.glob("OneDrive*")):
            if (onedrive / subpasta).is_dir():
                return str(onedrive / subpasta)
    return str(Path.home() / "Documents" / "LAMINAS PROSPECT")


DEFAULTS: dict = {
    # Pasta raiz das lâminas: cada subpasta é uma pasta de campanha
    # (corporativo, eventos, incentivo...) com as imagens.
    "pasta_laminas": _pasta_laminas_padrao(),
    # Pasta das apresentações enviadas como anexo (em branco = subpasta
    # APRESENTAÇÃO dentro da pasta das lâminas).
    "pasta_anexos": "",
    # Pasta -> nome do arquivo de apresentação ("" = sem anexo).
    "anexos_por_campanha": {},
    # Quantidade máxima de e-mails por dia e minutos entre um e outro.
    "limite_diario": 80,
    "intervalo_minutos": 3.0,
    # E-mail que recebe cópia (CC) nos contatos marcados antes do disparo.
    "email_copia": "",
    # Cópia oculta (CCO) em todos os envios, se preenchida.
    "copia_oculta": "",
    # Remetente das prospecções: caixa do subdomínio (ex.:
    # comercial@prospeccao.suaempresa.com.br), enviada por SMTP.
    "subdominio_envio": "",
    "remetente_email": "",
    "remetente_nome": "",
    # Para onde vão as respostas (Reply-To), ex.: o e-mail do domínio principal.
    "responder_para": "",
    "provedor_smtp": "outro",
    "smtp_host": "",
    "smtp_porta": 587,
    "smtp_seguranca": "starttls",
    "smtp_usuario": "",
    "smtp_senha": "",  # referência às Chaves do macOS (ver segredo.py)
    # Assinatura no fim do e-mail (o SMTP não usa a assinatura de nenhum app).
    "assinatura_smtp": "",
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
    if cfg.get("provedor_smtp") not in PROVEDORES_SMTP:
        cfg["provedor_smtp"] = "outro"
    return cfg


def salvar(cfg: dict, caminho: os.PathLike | str = ARQUIVO_CONFIG) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def mensagem_da_campanha(cfg: dict, campanha: str) -> dict:
    """Mensagem (assunto/textos) da pasta, ou a padrão se ela não tiver."""
    mensagens = cfg.get("mensagens") or {}
    padrao = mensagens.get(MENSAGEM_PADRAO) or DEFAULTS["mensagens"][MENSAGEM_PADRAO]
    propria = mensagens.get(campanha) if campanha else None
    return dict(propria or padrao)


def tem_mensagem_propria(cfg: dict, campanha: str) -> bool:
    return bool(campanha) and campanha in (cfg.get("mensagens") or {})


def dominio_do_email(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower() if "@" in (email or "") else ""


def normalizar_subdominio(valor: str) -> str:
    valor = (valor or "").strip().lower()
    for prefixo in ("https://", "http://", "www.", "@"):
        if valor.startswith(prefixo):
            valor = valor[len(prefixo):]
    return valor.strip("/ .")


def avisos_remetente(cfg: dict) -> list[str]:
    """O que falta ou não bate na configuração do remetente/SMTP."""
    avisos = []
    sub = normalizar_subdominio(cfg.get("subdominio_envio", ""))
    remetente = (cfg.get("remetente_email") or "").strip()
    if not remetente:
        avisos.append("Informe o e-mail remetente (Configurações › Remetente).")
    if sub and remetente and dominio_do_email(remetente) != sub:
        avisos.append(f"O remetente {remetente} não é do subdomínio {sub}.")
    faltando = [rotulo for chave, rotulo in (("smtp_host", "servidor"), ("smtp_usuario", "usuário"),
                                              ("smtp_senha", "senha")) if not cfg.get(chave)]
    if faltando:
        avisos.append("SMTP sem " + ", ".join(faltando) + ".")
    return avisos


def descricao_remetente(cfg: dict) -> str:
    """Texto curto do remetente em uso (tela, resumo e histórico)."""
    remetente = (cfg.get("remetente_email") or "").strip()
    return f"{remetente} (SMTP)" if remetente else "(remetente não configurado)"


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
