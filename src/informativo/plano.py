"""Contagem regressiva do plano gratuito do banco de dados (Render).

O PostgreSQL gratuito do Render expira após um número de dias a partir da
criação. Guardamos a **data/hora de início** (quando conectamos o banco) e o
total de dias (padrão 30) em ``configuracoes``; a tela inicial mostra ao
Administrador quantos **dias e horas** faltam para migrar ao plano pago.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .settings_repo import SettingsRepository

CFG_DB_INICIO = "db_free_inicio"   # data/hora ISO (YYYY-MM-DD[THH:MM]) do início
CFG_DB_DIAS = "db_free_dias"       # total de dias gratuitos (padrão 30)
PADRAO_DIAS = 30

# Início real da operação: data/hora em que o PostgreSQL gratuito foi
# provisionado no Render (commit a2dda9e "Suporte a PostgreSQL + banco gratuito
# no Render", 2026-09-14 22:51 UTC). Correção única; ajustável em Configurações.
DATA_INICIO_OPERACAO = "2026-09-14T22:51"


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_inicio(txt: Optional[str]) -> Optional[datetime]:
    """Interpreta a data/hora de início (aceita só data ou data+hora)."""
    if not txt:
        return None
    txt = txt.strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Última tentativa: ISO nativo (com offset, etc.).
    try:
        d = datetime.fromisoformat(txt.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def garantir_inicio(settings: SettingsRepository) -> str:
    """Define o início como agora (minuto) se ainda não houver um. Devolve-o."""
    atual = settings.get(CFG_DB_INICIO)
    if _parse_inicio(atual) is None:
        atual = agora_utc().strftime("%Y-%m-%dT%H:%M")
        settings.set(CFG_DB_INICIO, atual)
    return atual


def contagem_regressiva(settings: SettingsRepository,
                        agora: Optional[datetime] = None) -> Optional[dict]:
    """Situação do plano free (com hora), ou ``None`` se não configurado.

    Campos: ``inicio`` e ``expira`` (datetime), ``dias_total``,
    ``restantes_dias`` + ``restantes_horas`` (parte fracionária em horas),
    ``restante_horas_total``, ``pct`` (0–100 do tempo consumido),
    ``expirado``/``alerta`` e ``atraso_dias`` quando vencido.
    """
    inicio = _parse_inicio(settings.get(CFG_DB_INICIO))
    if inicio is None:
        return None
    try:
        dias_total = int(settings.get(CFG_DB_DIAS, str(PADRAO_DIAS)) or PADRAO_DIAS)
    except (TypeError, ValueError):
        dias_total = PADRAO_DIAS
    dias_total = max(1, dias_total)

    agora = agora or agora_utc()
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    expira = inicio + timedelta(days=dias_total)
    restante = expira - agora
    segs = restante.total_seconds()
    total_segs = dias_total * 86400
    decorrido = max(0.0, min(total_segs, (agora - inicio).total_seconds()))

    expirado = segs < 0
    restantes_dias = 0 if expirado else int(segs // 86400)
    restantes_horas = 0 if expirado else int((segs % 86400) // 3600)
    return {
        "inicio": inicio,
        "expira": expira,
        "dias_total": dias_total,
        "restantes_dias": restantes_dias,
        "restantes_horas": restantes_horas,
        "restante_horas_total": max(0, int(segs // 3600)),
        "pct": round(decorrido / total_segs * 100),
        "expirado": expirado,
        "alerta": (not expirado) and segs <= 7 * 86400,
        "atraso_dias": int((-segs) // 86400) if expirado else 0,
    }
