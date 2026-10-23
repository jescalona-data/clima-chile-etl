"""Punto de entrada: python -m clima_etl"""
import logging
import sys

import pandas as pd

from .extract import ErrorExtraccion
from .logger import configurar_logging
from .pipeline import ejecutar
from .sheets import ErrorSheets

log = logging.getLogger("clima_etl")


def main() -> int:
    configurar_logging()
    try:
        _, resumen = ejecutar()
    except (ErrorExtraccion, ErrorSheets) as e:
        log.error("El pipeline terminó con error: %s", e)
        return 1

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("\nResumen por ciudad:\n")
    print(resumen.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())