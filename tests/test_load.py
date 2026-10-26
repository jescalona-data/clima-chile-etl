"""Tests de load.py: la carga en SQLite debe ser idempotente."""
import sqlite3
from contextlib import closing

from clima_etl.load import guardar_en_sqlite


def _consultar(ruta, sql):
    with closing(sqlite3.connect(ruta)) as con:
        return con.execute(sql).fetchall()


def test_guardar_crea_la_base_y_las_filas(tabla_diaria, tmp_path):
    ruta = tmp_path / "subcarpeta" / "clima.db"  # la carpeta aún no existe

    guardadas = guardar_en_sqlite(tabla_diaria, ruta)

    assert guardadas == len(tabla_diaria)
    assert _consultar(ruta, "SELECT COUNT(*) FROM clima_diario") == [(5,)]


def test_guardar_dos_veces_no_duplica(tabla_diaria, tmp_path):
    ruta = tmp_path / "clima.db"

    guardar_en_sqlite(tabla_diaria, ruta)
    guardar_en_sqlite(tabla_diaria, ruta)

    assert _consultar(ruta, "SELECT COUNT(*) FROM clima_diario") == [(5,)]


def test_guardar_de_nuevo_actualiza_los_valores(tabla_diaria, tmp_path):
    ruta = tmp_path / "clima.db"
    guardar_en_sqlite(tabla_diaria, ruta)

    corregida = tabla_diaria.copy()
    corregida.loc[corregida["fecha"] == "2026-10-18", "lluvia_mm"] = 99.0
    guardar_en_sqlite(corregida, ruta)

    assert _consultar(ruta, "SELECT lluvia_mm FROM clima_diario WHERE fecha = '2026-10-18'") == [(99.0,)]
    assert _consultar(ruta, "SELECT COUNT(*) FROM clima_diario") == [(5,)]


def test_los_datos_faltantes_se_guardan_como_null(respuesta_api, hoy, tmp_path):
    from clima_etl.transform import construir_tabla_diaria

    crudo = {"X": respuesta_api(["2026-10-19"], lluvia=[None])}
    tabla = construir_tabla_diaria(crudo, hoy, 10, 50)
    ruta = tmp_path / "clima.db"

    guardar_en_sqlite(tabla, ruta)

    assert _consultar(ruta, "SELECT lluvia_mm FROM clima_diario") == [(None,)]
