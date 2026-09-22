"""Testes do regressivo do plano gratuito do banco (Render), com hora."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from informativo.db import Database, init_db
from informativo.plano import (
    CFG_DB_DIAS, CFG_DB_INICIO, agora_utc, contagem_regressiva, garantir_inicio,
)
from informativo.settings_repo import SettingsRepository


@pytest.fixture()
def settings(tmp_path):
    with Database(f"sqlite:///{tmp_path}/p.db") as db:
        init_db(db)
        yield SettingsRepository(db)


def test_garantir_inicio_define_agora(settings):
    assert settings.get(CFG_DB_INICIO) is None
    inicio = garantir_inicio(settings)
    assert inicio.startswith(agora_utc().strftime("%Y-%m-%d"))
    # idempotente: não sobrescreve
    settings.set(CFG_DB_INICIO, "2026-01-01T10:00")
    assert garantir_inicio(settings) == "2026-01-01T10:00"


def test_contagem_com_dias_e_horas(settings):
    settings.set(CFG_DB_INICIO, "2026-09-14T22:51")
    settings.set(CFG_DB_DIAS, "30")
    # "agora" fixo: 8 dias e 3h após o início
    agora = datetime(2026, 9, 23, 1, 51, tzinfo=timezone.utc)
    c = contagem_regressiva(settings, agora=agora)
    assert c["dias_total"] == 30
    assert c["expira"] == datetime(2026, 10, 14, 22, 51, tzinfo=timezone.utc)
    # faltam 30 - 8 dias e 3h = 21 dias e 21 horas
    assert c["restantes_dias"] == 21
    assert c["restantes_horas"] == 21
    assert c["expirado"] is False


def test_aceita_data_sem_hora(settings):
    settings.set(CFG_DB_INICIO, "2026-09-14")  # sem hora -> 00:00 UTC
    c = contagem_regressiva(settings, agora=datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc))
    assert c["inicio"] == datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    assert c["restantes_dias"] == 29 and c["restantes_horas"] == 18


def test_alerta_e_expirado(settings):
    settings.set(CFG_DB_DIAS, "30")
    settings.set(CFG_DB_INICIO, "2026-09-14T00:00")
    # faltando ~5 dias -> alerta
    c = contagem_regressiva(settings, agora=datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc))
    assert c["alerta"] is True and c["expirado"] is False
    # já venceu há 3 dias
    c2 = contagem_regressiva(settings, agora=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc))
    assert c2["expirado"] is True and c2["atraso_dias"] == 3


def test_sem_inicio_retorna_none(settings):
    assert contagem_regressiva(settings) is None
