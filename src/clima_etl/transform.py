"""TRANSFORMAR: funciones puras (sin internet ni archivos), fáciles de testear."""
from datetime import date, timedelta

import pandas as pd

RENOMBRAR = {
    "time": "fecha",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum": "lluvia_mm",
    "wind_speed_10m_max": "viento_max_kmh",
}
NUMERICAS = ["temp_max", "temp_min", "lluvia_mm", "viento_max_kmh"]

# Semáforo según los días de riesgo previstos en el pronóstico
UMBRAL_RIESGO_MEDIO = 1  # 1 o 2 días  -> Medio
UMBRAL_RIESGO_ALTO = 3   # 3 o más días -> Alto

COLUMNAS_DIARIAS = [
    "ciudad", "fecha", "tipo", "temp_max", "temp_min", "temp_media", "rango_termico",
    "lluvia_mm", "viento_max_kmh", "lluvia_fuerte", "viento_fuerte", "riesgo_operativo",
]


def respuesta_a_dataframe(ciudad: str, respuesta: dict) -> pd.DataFrame:
    """Convierte la respuesta JSON de una ciudad en una tabla (una fila por día)."""
    df = pd.DataFrame(respuesta["daily"]).rename(columns=RENOMBRAR)
    df.insert(0, "ciudad", ciudad)
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%Y-%m-%d")
    for col in NUMERICAS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def construir_tabla_diaria(
    crudo: dict[str, dict],
    hoy: date,
    lluvia_fuerte_mm: float,
    viento_fuerte_kmh: float,
) -> pd.DataFrame:
    """Une todas las ciudades y agrega columnas calculadas e indicadores de riesgo."""
    df = pd.concat(
        [respuesta_a_dataframe(ciudad, r) for ciudad, r in crudo.items()],
        ignore_index=True,
    )
    df["tipo"] = df["fecha"].apply(lambda f: "historico" if f < hoy.isoformat() else "pronostico")
    df["temp_media"] = ((df["temp_max"] + df["temp_min"]) / 2).round(1)
    df["rango_termico"] = (df["temp_max"] - df["temp_min"]).round(1)
    df["lluvia_fuerte"] = (df["lluvia_mm"] >= lluvia_fuerte_mm).astype(int)
    df["viento_fuerte"] = (df["viento_max_kmh"] >= viento_fuerte_kmh).astype(int)
    df["riesgo_operativo"] = ((df["lluvia_fuerte"] + df["viento_fuerte"]) > 0).astype(int)
    return df[COLUMNAS_DIARIAS].sort_values(["ciudad", "fecha"]).reset_index(drop=True)


def resumen_por_ciudad(df: pd.DataFrame, hoy: date) -> pd.DataFrame:
    """Indicadores por ciudad: últimos 30 días y riesgo previsto para los próximos días."""
    hist = df[df["tipo"] == "historico"]
    corte_7d = (hoy - timedelta(days=7)).isoformat()
    ult_7d = hist[hist["fecha"] >= corte_7d]
    prox = df[df["tipo"] == "pronostico"]

    g30 = hist.groupby("ciudad")
    resumen = pd.concat(
        {
            "temp_media_30d": g30["temp_media"].mean(),
            "lluvia_7d_mm": ult_7d.groupby("ciudad")["lluvia_mm"].sum(),
            "lluvia_30d_mm": g30["lluvia_mm"].sum(),
            "dias_lluvia_fuerte_30d": g30["lluvia_fuerte"].sum(),
            "dias_riesgo_30d": g30["riesgo_operativo"].sum(),
            "dias_riesgo_proximos": prox.groupby("ciudad")["riesgo_operativo"].sum(),
        },
        axis=1,
    )
    resumen = resumen.fillna(0).round(1).reset_index().rename(columns={"index": "ciudad"})
    for col in ["dias_lluvia_fuerte_30d", "dias_riesgo_30d", "dias_riesgo_proximos"]:
        resumen[col] = resumen[col].astype(int)
    return resumen

def nivel_riesgo(dias_riesgo: int) -> str:
    """Traduce una cantidad de días de riesgo a un nivel de semáforo."""
    if dias_riesgo >= UMBRAL_RIESGO_ALTO:
        return "🔴 Alto"
    if dias_riesgo >= UMBRAL_RIESGO_MEDIO:
        return "🟡 Medio"
    return "🟢 Bajo"


def agregar_nivel_riesgo(resumen: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una copia del resumen con la columna `nivel_riesgo` (semáforo)."""
    salida = resumen.copy()
    salida.insert(1, "nivel_riesgo", salida["dias_riesgo_proximos"].apply(nivel_riesgo))
    return salida