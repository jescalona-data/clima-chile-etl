"""Tests de config.py: lectura de settings.yaml y variables de entorno."""
import pytest

from clima_etl import config
from clima_etl.config import cargar_settings


@pytest.fixture(autouse=True)
def sin_dotenv_real(monkeypatch):
    """Evita que el .env real de quien corre los tests contamine los resultados."""
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("SHEET_NAME", raising=False)


YAML_MINIMO = """
ciudades:
  {ciudades}
api:
  url: https://api.test
  dias_pasados: 5
  dias_futuros: 2
  zona_horaria: America/Santiago
  variables_diarias: [temperature_2m_max]
  timeout_segundos: 5
  reintentos: 2
umbrales:
  lluvia_fuerte_mm: 8
  viento_fuerte_kmh: 40
base_de_datos:
  ruta: data/test.db
"""


def test_el_settings_yaml_del_proyecto_es_valido():
    """Si alguien edita config/settings.yaml con un error, este test lo detecta."""
    s = cargar_settings()

    assert len(s.ciudades) >= 1
    for ciudad in s.ciudades:
        assert -90 <= ciudad.latitud <= 90
        assert -180 <= ciudad.longitud <= 180
    assert s.lluvia_fuerte_mm > 0
    assert s.viento_fuerte_kmh > 0
    assert s.reintentos >= 1


def test_sin_variables_de_entorno_no_hay_credenciales():
    s = cargar_settings()

    assert s.ruta_credenciales is None
    assert s.nombre_sheet is None


def test_lee_credenciales_y_sheet_desde_el_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", str(tmp_path / "cred.json"))
    monkeypatch.setenv("SHEET_NAME", "mi-sheet")

    s = cargar_settings()

    assert s.ruta_credenciales == tmp_path / "cred.json"
    assert s.nombre_sheet == "mi-sheet"


def test_archivo_de_configuracion_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError, match="configuración"):
        cargar_settings(tmp_path / "no_existe.yaml")


def test_lee_un_yaml_propio(tmp_path):
    ruta = tmp_path / "s.yaml"
    ruta.write_text(YAML_MINIMO.format(
        ciudades="- {nombre: Lima, latitud: -12.04, longitud: -77.03}"), encoding="utf-8")

    s = cargar_settings(ruta)

    assert s.ciudades[0].nombre == "Lima"
    assert s.dias_pasados == 5
    assert s.lluvia_fuerte_mm == 8.0


def test_yaml_sin_ciudades_da_error_claro(tmp_path):
    ruta = tmp_path / "s.yaml"
    ruta.write_text(YAML_MINIMO.format(ciudades="[]"), encoding="utf-8")

    with pytest.raises(ValueError, match="ciudades"):
        cargar_settings(ruta)
