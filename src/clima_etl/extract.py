"""EXTRAER: consulta la API de Open-Meteo, con timeouts y reintentos."""
import logging
import time

import requests

from .config import Ciudad, Settings

log = logging.getLogger(__name__)


class ErrorExtraccion(Exception):
    """No se pudo obtener datos de la API."""


def _parametros(settings: Settings, ciudad: Ciudad) -> dict:
    return {
        "latitude": ciudad.latitud,
        "longitude": ciudad.longitud,
        "daily": ",".join(settings.variables_diarias),
        "timezone": settings.zona_horaria,
        "past_days": settings.dias_pasados,
        "forecast_days": settings.dias_futuros,
    }


def extraer_ciudad(sesion: requests.Session, settings: Settings, ciudad: Ciudad) -> dict:
    """Pide los datos de una ciudad. Reintenta con espera creciente si falla."""
    params = _parametros(settings, ciudad)
    ultimo_error: Exception | None = None

    for intento in range(1, settings.reintentos + 1):
        try:
            respuesta = sesion.get(settings.api_url, params=params, timeout=settings.timeout)
            respuesta.raise_for_status()
            datos = respuesta.json()
            if "daily" not in datos:
                raise ErrorExtraccion(f"Respuesta inesperada para {ciudad.nombre}: {list(datos)}")
            return datos
        except requests.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else None
            # Un error 4xx (salvo 429) es un problema de la consulta: reintentar no sirve.
            if codigo is not None and 400 <= codigo < 500 and codigo != 429:
                raise ErrorExtraccion(f"{ciudad.nombre}: la API rechazó la consulta ({codigo})") from e
            ultimo_error = e
        except requests.RequestException as e:
            ultimo_error = e

        if intento < settings.reintentos:
            espera = 2 ** intento
            log.warning("%s: intento %d/%d falló (%s). Reintento en %ds",
                        ciudad.nombre, intento, settings.reintentos, ultimo_error, espera)
            time.sleep(espera)

    raise ErrorExtraccion(f"No se pudo obtener datos de {ciudad.nombre}") from ultimo_error


def extraer_todo(settings: Settings) -> dict[str, dict]:
    """Devuelve {nombre_ciudad: respuesta_cruda_de_la_API}."""
    crudo: dict[str, dict] = {}
    with requests.Session() as sesion:
        for ciudad in settings.ciudades:
            log.info("Extrayendo %s", ciudad.nombre)
            crudo[ciudad.nombre] = extraer_ciudad(sesion, settings, ciudad)
    return crudo