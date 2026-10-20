"""Carga y validación de la configuración (config/settings.yaml)."""
from dataclasses import dataclass
from pathlib import Path

import yaml

# src/clima_etl/config.py -> la raíz del proyecto está 3 niveles arriba
RAIZ = Path(__file__).resolve().parents[2]
RUTA_SETTINGS = RAIZ / "config" / "settings.yaml"


@dataclass(frozen=True)
class Ciudad:
    nombre: str
    latitud: float
    longitud: float


@dataclass(frozen=True)
class Settings:
    ciudades: tuple[Ciudad, ...]
    api_url: str
    dias_pasados: int
    dias_futuros: int
    zona_horaria: str
    variables_diarias: tuple[str, ...]
    timeout: int
    reintentos: int
    lluvia_fuerte_mm: float
    viento_fuerte_kmh: float
    ruta_db: Path


def cargar_settings(ruta: Path = RUTA_SETTINGS) -> Settings:
    if not ruta.exists():
        raise FileNotFoundError(f"No encuentro el archivo de configuración: {ruta}")

    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    ciudades = tuple(
        Ciudad(c["nombre"], float(c["latitud"]), float(c["longitud"]))
        for c in cfg["ciudades"]
    )
    if not ciudades:
        raise ValueError("settings.yaml no tiene ciudades configuradas")

    api = cfg["api"]
    umbrales = cfg["umbrales"]
    return Settings(
        ciudades=ciudades,
        api_url=api["url"],
        dias_pasados=int(api["dias_pasados"]),
        dias_futuros=int(api["dias_futuros"]),
        zona_horaria=api["zona_horaria"],
        variables_diarias=tuple(api["variables_diarias"]),
        timeout=int(api["timeout_segundos"]),
        reintentos=int(api["reintentos"]),
        lluvia_fuerte_mm=float(umbrales["lluvia_fuerte_mm"]),
        viento_fuerte_kmh=float(umbrales["viento_fuerte_kmh"]),
        ruta_db=RAIZ / cfg["base_de_datos"]["ruta"],
    )