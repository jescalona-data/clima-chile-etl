"""Fixtures compartidas por todos los tests (datos inventados, sin internet)."""
from datetime import date

import pytest

from clima_etl.config import Ciudad, Settings
from clima_etl.transform import construir_tabla_diaria

HOY = date(2026, 10, 20)


@pytest.fixture
def hoy():
    return HOY


@pytest.fixture
def respuesta_api():
    """Fábrica de respuestas con el mismo formato que devuelve Open-Meteo."""

    def _crear(fechas, tmax=None, tmin=None, lluvia=None, viento=None):
        n = len(fechas)
        return {"daily": {
            "time": list(fechas),
            "temperature_2m_max": tmax or [20.0] * n,
            "temperature_2m_min": tmin or [10.0] * n,
            "precipitation_sum": lluvia or [0.0] * n,
            "wind_speed_10m_max": viento or [15.0] * n,
        }}

    return _crear


@pytest.fixture
def settings(tmp_path):
    return Settings(
        ciudades=(Ciudad("Testville", -33.0, -70.0),),
        api_url="https://api.test/v1/forecast",
        dias_pasados=3,
        dias_futuros=2,
        zona_horaria="America/Santiago",
        variables_diarias=("temperature_2m_max", "temperature_2m_min",
                           "precipitation_sum", "wind_speed_10m_max"),
        timeout=5,
        reintentos=3,
        lluvia_fuerte_mm=10.0,
        viento_fuerte_kmh=50.0,
        ruta_db=tmp_path / "clima.db",
    )


@pytest.fixture
def tabla_diaria(respuesta_api, hoy):
    """Tabla diaria lista: 3 días históricos y 2 de pronóstico, una sola ciudad."""
    fechas = ["2026-10-17", "2026-10-18", "2026-10-19", "2026-10-20", "2026-10-21"]
    crudo = {"Testville": respuesta_api(fechas, lluvia=[0.0, 12.0, 3.0, 0.0, 25.0])}
    return construir_tabla_diaria(crudo, hoy, lluvia_fuerte_mm=10, viento_fuerte_kmh=50)
