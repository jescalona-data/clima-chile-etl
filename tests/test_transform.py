"""Tests de transform.py: funciones puras, sin internet ni archivos."""
import pandas as pd
import pytest

from clima_etl.transform import (
    agregar_nivel_riesgo,
    construir_tabla_diaria,
    nivel_riesgo,
    respuesta_a_dataframe,
    resumen_por_ciudad,
)


def test_respuesta_a_dataframe_renombra_columnas_y_convierte_nulos(respuesta_api):
    respuesta = respuesta_api(["2026-10-19", "2026-10-20"], lluvia=[None, 2.0])

    df = respuesta_a_dataframe("Santiago", respuesta)

    assert list(df.columns) == [
        "ciudad", "fecha", "temp_max", "temp_min", "lluvia_mm", "viento_max_kmh"
    ]
    assert pd.isna(df.loc[0, "lluvia_mm"])  # un dato faltante queda como NaN, no rompe
    assert df.loc[1, "lluvia_mm"] == 2.0


@pytest.mark.parametrize("lluvia, viento, esperado", [
    (9.9, 49.9, 0),   # justo por debajo de ambos umbrales
    (10.0, 10.0, 1),  # lluvia exactamente en el umbral: cuenta (>=)
    (0.0, 50.0, 1),   # viento exactamente en el umbral: cuenta (>=)
    (12.0, 60.0, 1),  # ambos superados
])
def test_riesgo_operativo_usa_umbrales_inclusivos(respuesta_api, hoy, lluvia, viento, esperado):
    crudo = {"X": respuesta_api(["2026-10-19"], lluvia=[lluvia], viento=[viento])}

    df = construir_tabla_diaria(crudo, hoy, lluvia_fuerte_mm=10, viento_fuerte_kmh=50)

    assert df.loc[0, "riesgo_operativo"] == esperado


def test_dato_faltante_no_cuenta_como_riesgo(respuesta_api, hoy):
    crudo = {"X": respuesta_api(["2026-10-19"], lluvia=[None], viento=[None])}

    df = construir_tabla_diaria(crudo, hoy, lluvia_fuerte_mm=10, viento_fuerte_kmh=50)

    assert df.loc[0, "riesgo_operativo"] == 0


def test_hoy_y_los_dias_futuros_son_pronostico(respuesta_api, hoy):
    fechas = ["2026-10-19", "2026-10-20", "2026-10-21"]
    crudo = {"X": respuesta_api(fechas)}

    df = construir_tabla_diaria(crudo, hoy, 10, 50)

    assert df["tipo"].tolist() == ["historico", "pronostico", "pronostico"]


def test_temperatura_media_y_rango_termico(respuesta_api, hoy):
    crudo = {"X": respuesta_api(["2026-10-19"], tmax=[24.0], tmin=[10.0])}

    df = construir_tabla_diaria(crudo, hoy, 10, 50)

    assert df.loc[0, "temp_media"] == 17.0
    assert df.loc[0, "rango_termico"] == 14.0


def test_construir_tabla_une_varias_ciudades_ordenadas(respuesta_api, hoy):
    crudo = {"Zeta": respuesta_api(["2026-10-19"]), "Alfa": respuesta_api(["2026-10-19"])}

    df = construir_tabla_diaria(crudo, hoy, 10, 50)

    assert df["ciudad"].tolist() == ["Alfa", "Zeta"]


def test_resumen_suma_lluvia_de_7_y_30_dias(respuesta_api, hoy):
    # 10 días históricos (del 10 al 19 de octubre) con 1 mm cada uno + 2 de pronóstico
    fechas = [f"2026-10-{d:02d}" for d in range(10, 22)]
    crudo = {"X": respuesta_api(fechas, lluvia=[1.0] * len(fechas))}
    diaria = construir_tabla_diaria(crudo, hoy, 10, 50)

    resumen = resumen_por_ciudad(diaria, hoy)

    fila = resumen.iloc[0]
    assert fila["lluvia_30d_mm"] == 10.0  # los 10 días históricos
    assert fila["lluvia_7d_mm"] == 7.0    # solo los últimos 7 días históricos


def test_resumen_separa_riesgo_pasado_y_previsto(tabla_diaria, hoy):
    resumen = resumen_por_ciudad(tabla_diaria, hoy).iloc[0]

    assert resumen["dias_riesgo_30d"] == 1       # solo el 18 (12 mm) en el pasado
    assert resumen["dias_riesgo_proximos"] == 1  # solo el 21 (25 mm) en el pronóstico


@pytest.mark.parametrize("dias, esperado", [
    (0, "🟢 Bajo"),
    (1, "🟡 Medio"),
    (2, "🟡 Medio"),
    (3, "🔴 Alto"),
    (7, "🔴 Alto"),
])
def test_nivel_riesgo(dias, esperado):
    assert nivel_riesgo(dias) == esperado


def test_agregar_nivel_riesgo_no_modifica_el_original(tabla_diaria, hoy):
    resumen = resumen_por_ciudad(tabla_diaria, hoy)

    con_nivel = agregar_nivel_riesgo(resumen)

    assert "nivel_riesgo" not in resumen.columns
    assert list(con_nivel.columns)[:2] == ["ciudad", "nivel_riesgo"]
