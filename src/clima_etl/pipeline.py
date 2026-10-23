"""Orquesta el pipeline completo: extraer -> transformar -> cargar."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import Settings, cargar_settings
from .extract import extraer_todo
from .load import guardar_en_sqlite
from .sheets import publicar_en_sheets
from .transform import agregar_nivel_riesgo, construir_tabla_diaria, resumen_por_ciudad

log = logging.getLogger(__name__)


def _publicar(settings: Settings, diaria: pd.DataFrame, resumen: pd.DataFrame) -> None:
    """Publica en Google Sheets si hay credenciales configuradas en el .env."""
    if settings.ruta_credenciales is None or not settings.nombre_sheet:
        log.info("Google Sheets no configurado (.env): se omite la publicación")
        return
    log.info("Publicando en Google Sheets: %s", settings.nombre_sheet)
    publicar_en_sheets(
        settings.ruta_credenciales, settings.nombre_sheet, diaria, agregar_nivel_riesgo(resumen)
    )
    log.info("Google Sheets actualizado")


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
    _publicar(settings, diaria, resumen)

    log.info("Pipeline terminado: %d ciudades, %d filas diarias", len(resumen), len(diaria))
    return diaria, resumen