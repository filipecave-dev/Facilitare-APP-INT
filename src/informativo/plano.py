"""Contagem regressiva do plano gratuito do banco de dados (Render).

O PostgreSQL gratuito do Render expira após um número de dias a partir da
criação. Guardamos a **data de início** (quando conectamos o banco) e o total
de dias (padrão 30) em ``configuracoes``; a tela inicial mostra ao
Administrador quantos dias faltam para migrar ao plano pago.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from .settings_repo import SettingsRepository

CFG_DB_INICIO = "db_free_inicio"   # data ISO (YYYY-MM-DD) da conexão do banco
CFG_DB_DIAS = "db_free_dias"       # total de dias gratuitos (padrão 30)
PADRAO_DIAS = 30

# Início real da operação: data em que o PostgreSQL gratuito foi provisionado
# no Render (commit a2dda9e "Suporte a PostgreSQL + banco gratuito no Render").
# Usada como correção única do contador; ajustável depois em Configurações.
DATA_INICIO_OPERACAO = "2026-09-14"


def hoje() -> date:
    return datetime.now(timezone.utc).date()


def _parse_data(txt: Optional[str]) -> Optional[date]:
    if not txt:
        return None
    try:
        return date.fromisoformat(txt.strip()[:10])
    except ValueError:
        return None


def garantir_inicio(settings: SettingsRepository) -> str:
    """Define a data de início como hoje se ainda não houver uma. Devolve-a."""
    atual = settings.get(CFG_DB_INICIO)
    if not _parse_data(atual):
        atual = hoje().isoformat()
        settings.set(CFG_DB_INICIO, atual)
    return atual


def contagem_regressiva(settings: SettingsRepository) -> Optional[dict]:
    """Devolve a situação do plano free, ou ``None`` se não configurado.

    Campos: ``inicio``, ``dias_total``, ``expira`` (date), ``restantes`` (int,
    pode ser negativo), ``decorridos`` e ``pct`` (0–100 do tempo consumido).
    """
    inicio = _parse_data(settings.get(CFG_DB_INICIO))
    if inicio is None:
        return None
    try:
        dias_total = int(settings.get(CFG_DB_DIAS, str(PADRAO_DIAS)) or PADRAO_DIAS)
    except (TypeError, ValueError):
        dias_total = PADRAO_DIAS
    dias_total = max(1, dias_total)

    from datetime import timedelta

    expira = inicio + timedelta(days=dias_total)
    restantes = (expira - hoje()).days
    decorridos = max(0, min(dias_total, (hoje() - inicio).days))
    pct = round(decorridos / dias_total * 100)
    return {
        "inicio": inicio,
        "dias_total": dias_total,
        "expira": expira,
        "restantes": restantes,
        "decorridos": decorridos,
        "pct": pct,
        "expirado": restantes < 0,
        "alerta": restantes <= 7,
    }
