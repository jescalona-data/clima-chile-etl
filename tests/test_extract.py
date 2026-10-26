"""Tests de extract.py: reintentos y manejo de errores, con una sesión falsa (sin internet)."""
import pytest
import requests

from clima_etl import extract
from clima_etl.extract import ErrorExtraccion, extraer_ciudad

OK = {"daily": {"time": ["2026-10-19"]}}


class RespuestaFalsa:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = OK if payload is None else payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


class SesionFalsa:
    """Responde según un guion: cada llamada consume el siguiente paso."""

    def __init__(self, guion):
        self.guion = list(guion)
        self.llamadas = 0

    def get(self, url, params=None, timeout=None):
        self.llamadas += 1
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return paso


@pytest.fixture
def esperas(monkeypatch):
    """Evita esperar de verdad y registra cuántos segundos se habrían esperado."""
    registro = []
    monkeypatch.setattr(extract.time, "sleep", registro.append)
    return registro


def test_devuelve_los_datos_si_todo_sale_bien(settings):
    sesion = SesionFalsa([RespuestaFalsa()])

    datos = extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert datos == OK
    assert sesion.llamadas == 1


def test_reintenta_ante_caida_de_conexion_y_luego_funciona(settings, esperas):
    sesion = SesionFalsa([requests.ConnectionError(), requests.Timeout(), RespuestaFalsa()])

    datos = extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert datos == OK
    assert sesion.llamadas == 3


@pytest.mark.parametrize("codigo", [429, 500, 503])
def test_reintenta_ante_errores_temporales(settings, esperas, codigo):
    sesion = SesionFalsa([RespuestaFalsa(codigo), RespuestaFalsa()])

    datos = extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert datos == OK
    assert sesion.llamadas == 2


@pytest.mark.parametrize("codigo", [400, 401, 404])
def test_no_reintenta_ante_errores_de_la_consulta(settings, esperas, codigo):
    sesion = SesionFalsa([RespuestaFalsa(codigo)])

    with pytest.raises(ErrorExtraccion, match=str(codigo)):
        extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert sesion.llamadas == 1  # un 4xx no se soluciona reintentando
    assert esperas == []


def test_falla_despues_de_agotar_los_reintentos(settings, esperas):
    sesion = SesionFalsa([requests.ConnectionError()] * settings.reintentos)

    with pytest.raises(ErrorExtraccion, match="Testville"):
        extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert sesion.llamadas == settings.reintentos


def test_la_espera_entre_reintentos_crece(settings, esperas):
    sesion = SesionFalsa([requests.ConnectionError()] * settings.reintentos)

    with pytest.raises(ErrorExtraccion):
        extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert esperas == [2, 4]  # no espera después del último intento


def test_respuesta_sin_datos_diarios_es_un_error(settings, esperas):
    sesion = SesionFalsa([RespuestaFalsa(payload={"error": True})])

    with pytest.raises(ErrorExtraccion, match="inesperada"):
        extraer_ciudad(sesion, settings, settings.ciudades[0])

    assert sesion.llamadas == 1
