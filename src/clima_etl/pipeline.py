"""Orquesta el pipeline completo: extraer -> transformar -> cargar."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import Settings, cargar_settings
from .extract import extraer_todo
from .load import guardar_en_sqlite
from .transform import construir_tabla_diaria, resumen_por_ciudad

log = logging.getLogger(__name__)


def ejecutar(settings: Settings | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    settings = settings or cargar_settings()
    hoy = datetime.now(ZoneInfo(settings.zona_horaria)).date()
    log.info("Inicio del pipeline (fecha de referencia: %s)", hoy)

    crudo = extraer_todo(settings)
    diaria = construir_tabla_diaria(
        crudo, hoy, settings.lluvia_fuerte_mm, settings.viento_fuerte_kmh
    )
    guardar_en_sqlite(diaria, settings.ruta_db)
    resumen = resumen_por_ciudad(diaria, hoy)

    log.info("Pipeline terminado: %d ciudades, %d filas diarias", len(resumen), len(diaria))
    return diaria, resumen