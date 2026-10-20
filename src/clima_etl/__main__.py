"""Punto de entrada: python -m clima_etl"""
import pandas as pd

from .logger import configurar_logging
from .pipeline import ejecutar


def main() -> None:
    configurar_logging()
    _, resumen = ejecutar()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("\nResumen por ciudad:\n")
    print(resumen.to_string(index=False))


if __name__ == "__main__":
    main()