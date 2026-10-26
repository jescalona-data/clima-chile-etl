"""Test de integración: el pipeline completo con la API y Google Sheets reemplazados."""
import dataclasses
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from clima_etl import pipeline


@pytest.fixture
def crudo(respuesta_api, settings):
    """Datos que cruzan 'hoy' de verdad: 3 días atrás, hoy y 2 días adelante."""
    hoy = datetime.now(ZoneInfo(settings.zona_horaria)).date()
    fechas = [(hoy + timedelta(days=d)).isoformat() for d in range(-3, 3)]
    return {"Testville": respuesta_api(fechas, lluvia=[0, 0, 0, 0, 30, 0])}


def _filas_en_sqlite(ruta):
    with closing(sqlite3.connect(ruta)) as con:
        return con.execute("SELECT COUNT(*) FROM clima_diario").fetchone()[0]


def test_guarda_en_sqlite_y_omite_sheets_sin_credenciales(monkeypatch, settings, crudo):
    monkeypatch.setattr(pipeline, "extraer_todo", lambda s: crudo)
    llamadas = []
    monkeypatch.setattr(pipeline, "publicar_en_sheets", lambda *a: llamadas.append(a))

    diaria, resumen = pipeline.ejecutar(settings)

    assert len(diaria) == 6
    assert len(resumen) == 1
    assert _filas_en_sqlite(settings.ruta_db) == 6
    assert llamadas == []  # sin credenciales, no intenta publicar


def test_publica_en_sheets_si_hay_credenciales(monkeypatch, settings, crudo):
    monkeypatch.setattr(pipeline, "extraer_todo", lambda s: crudo)
    llamadas = []
    monkeypatch.setattr(pipeline, "publicar_en_sheets", lambda *a: llamadas.append(a))
    con_sheets = dataclasses.replace(
        settings, ruta_credenciales=Path("cred.json"), nombre_sheet="mi-sheet")

    pipeline.ejecutar(con_sheets)

    assert len(llamadas) == 1
    ruta, nombre, diaria, resumen = llamadas[0]
    assert nombre == "mi-sheet"
    assert "nivel_riesgo" in resumen.columns  # el semáforo se agrega antes de publicar


def test_ejecutar_dos_veces_no_duplica_filas(monkeypatch, settings, crudo):
    monkeypatch.setattr(pipeline, "extraer_todo", lambda s: crudo)

    pipeline.ejecutar(settings)
    pipeline.ejecutar(settings)

    assert _filas_en_sqlite(settings.ruta_db) == 6
