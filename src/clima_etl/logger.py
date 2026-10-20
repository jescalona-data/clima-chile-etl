"""Configuración de logging: mensajes con hora y nivel, en vez de print()."""
import logging
import sys


def configurar_logging(nivel: int = logging.INFO) -> None:
    logger = logging.getLogger("clima_etl")
    if logger.handlers:  # evita duplicar mensajes si se llama dos veces
        return
    logger.setLevel(nivel)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)