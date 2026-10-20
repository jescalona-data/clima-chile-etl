"""CARGAR: guarda los datos en SQLite (fuente de verdad, acumula histórico)."""
import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd

from .transform import COLUMNAS_DIARIAS

log = logging.getLogger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clima_diario (
    ciudad            TEXT    NOT NULL,
    fecha             TEXT    NOT NULL,   -- formato YYYY-MM-DD
    tipo              TEXT    NOT NULL,   -- 'historico' o 'pronostico'
    temp_max          REAL,
    temp_min          REAL,
    temp_media        REAL,
    rango_termico     REAL,
    lluvia_mm         REAL,
    viento_max_kmh    REAL,
    lluvia_fuerte     INTEGER NOT NULL DEFAULT 0,
    viento_fuerte     INTEGER NOT NULL DEFAULT 0,
    riesgo_operativo  INTEGER NOT NULL DEFAULT 0,
    actualizado_en    TEXT    NOT NULL,
    PRIMARY KEY (ciudad, fecha)
);
"""


def _sql_upsert() -> str:
    columnas = COLUMNAS_DIARIAS + ["actualizado_en"]
    marcas = ", ".join("?" for _ in columnas)
    actualizar = ", ".join(
        f"{c} = excluded.{c}" for c in columnas if c not in ("ciudad", "fecha")
    )
    return (
        f"INSERT INTO clima_diario ({', '.join(columnas)}) VALUES ({marcas}) "
        f"ON CONFLICT (ciudad, fecha) DO UPDATE SET {actualizar}"
    )


def guardar_en_sqlite(df: pd.DataFrame, ruta_db: Path) -> int:
    """Inserta o actualiza (por ciudad + fecha). Ejecutarlo dos veces no duplica filas."""
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now().isoformat(timespec="seconds")

    datos = df[COLUMNAS_DIARIAS].astype(object).where(df[COLUMNAS_DIARIAS].notna(), None)
    filas = [tuple(fila) + (ahora,) for fila in datos.values.tolist()]

    with closing(sqlite3.connect(ruta_db)) as con:
        with con:  # transacción: todo o nada
            con.execute(ESQUEMA)
            con.executemany(_sql_upsert(), filas)
    log.info("SQLite: %d filas guardadas en %s", len(filas), ruta_db)
    return len(filas)