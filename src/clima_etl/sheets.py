"""PUBLICAR: presenta los resultados en Google Sheets, con formato."""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import gspread
import pandas as pd

from .transform import UMBRAL_RIESGO_ALTO, UMBRAL_RIESGO_MEDIO

log = logging.getLogger(__name__)

# --- Paleta de colores ---
AZUL_OSCURO = {"red": 0.11, "green": 0.22, "blue": 0.36}
AZUL_CLARO = {"red": 0.93, "green": 0.96, "blue": 0.99}
BLANCO = {"red": 1.0, "green": 1.0, "blue": 1.0}
GRIS = {"red": 0.45, "green": 0.45, "blue": 0.45}
DEGRADE_AZUL = {"red": 0.42, "green": 0.65, "blue": 0.92}
DEGRADE_NARANJA = {"red": 0.98, "green": 0.74, "blue": 0.40}
DEGRADE_ROJO = {"red": 0.93, "green": 0.45, "blue": 0.42}
SEMAFORO_VERDE = {"red": 0.72, "green": 0.88, "blue": 0.73}
SEMAFORO_AMARILLO = {"red": 1.0, "green": 0.94, "blue": 0.62}
SEMAFORO_ROJO = {"red": 0.96, "green": 0.67, "blue": 0.64}
ALERTA_SUAVE = {"red": 0.98, "green": 0.80, "blue": 0.78}

HOJAS_POR_DEFECTO = {"Hoja 1", "Hoja1", "Sheet1"}

# Nombres de columna legibles para el Sheet (en la base de datos se mantienen los técnicos)
ENCABEZADOS = {
    "ciudad": "Ciudad", "fecha": "Fecha", "tipo": "Tipo",
    "temp_max": "Temp. máx (°C)", "temp_min": "Temp. mín (°C)",
    "temp_media": "Temp. media (°C)", "rango_termico": "Rango térmico (°C)",
    "lluvia_mm": "Lluvia (mm)", "viento_max_kmh": "Viento máx (km/h)",
    "lluvia_fuerte": "Lluvia fuerte", "viento_fuerte": "Viento fuerte",
    "riesgo_operativo": "Riesgo operativo",
    "nivel_riesgo": "Nivel de riesgo", "temp_media_30d": "Temp. media 30d (°C)",
    "lluvia_7d_mm": "Lluvia 7d (mm)", "lluvia_30d_mm": "Lluvia 30d (mm)",
    "dias_lluvia_fuerte_30d": "Días de lluvia fuerte (30d)",
    "dias_riesgo_30d": "Días de riesgo (30d)",
    "dias_riesgo_proximos": "Días de riesgo próximos",
}


class ErrorSheets(Exception):
    """No se pudo publicar en Google Sheets."""


@dataclass(frozen=True)
class FormatoHoja:
    """Describe cómo se ve una pestaña (qué columnas llevan color, número, etc.)."""
    gradientes: dict[int, dict] = field(default_factory=dict)       # columna -> color máximo
    formatos_numero: dict[int, str] = field(default_factory=dict)   # columna -> patrón
    textos_coloreados: tuple = ()                                   # (columna, texto, color)
    marcar_si_uno: tuple[int, ...] = ()                             # columnas 0/1: se pintan si valen 1
    cursiva_hasta: int = 0                                          # 'pronostico' en cursiva gris en las columnas [0, N)
    columnas_fijas: int = 0
    ancho_columna: int = 125


FORMATO_RESUMEN = FormatoHoja(
    gradientes={2: DEGRADE_NARANJA, 3: DEGRADE_AZUL, 4: DEGRADE_AZUL,
                5: DEGRADE_ROJO, 6: DEGRADE_ROJO, 7: DEGRADE_ROJO},
    formatos_numero={2: "0.0", 3: "0.0", 4: "0.0", 5: "0", 6: "0", 7: "0"},
    textos_coloreados=((1, "Bajo", SEMAFORO_VERDE),
                       (1, "Medio", SEMAFORO_AMARILLO),
                       (1, "Alto", SEMAFORO_ROJO)),
    columnas_fijas=1,
    ancho_columna=135,
)

FORMATO_DIARIO = FormatoHoja(
    gradientes={7: DEGRADE_AZUL, 8: DEGRADE_NARANJA},
    formatos_numero={3: "0.0", 4: "0.0", 5: "0.0", 6: "0.0", 7: "0.0", 8: "0.0"},
    marcar_si_uno=(9, 10, 11),
    cursiva_hasta=7,
    columnas_fijas=2,
    ancho_columna=125,
)


# ---------------------------------------------------------------- formato

def _rango(sid: int, fila_ini: int, fila_fin: int, col_ini: int, col_fin: int) -> dict:
    return {"sheetId": sid, "startRowIndex": fila_ini, "endRowIndex": fila_fin,
            "startColumnIndex": col_ini, "endColumnIndex": col_fin}


def _regla(sid: int, rango: dict, condicion: dict | None = None,
           formato: dict | None = None, gradiente: dict | None = None) -> dict:
    """Arma una regla de formato condicional (por condición o en degradé)."""
    regla: dict = {"ranges": [rango]}
    if gradiente:
        regla["gradientRule"] = {"minpoint": {"type": "MIN", "color": BLANCO},
                                 "maxpoint": {"type": "MAX", "color": gradiente}}
    else:
        regla["booleanRule"] = {"condition": condicion, "format": formato}
    return {"addConditionalFormatRule": {"rule": regla, "index": 0}}


def _pedidos_formato(sid: int, n_filas: int, n_cols: int, fmt: FormatoHoja) -> list[dict]:
    cuerpo = _rango(sid, 1, n_filas, 0, n_cols)
    pedidos: list[dict] = [
        # Encabezado: fondo azul oscuro, texto blanco en negrita
        {"repeatCell": {
            "range": _rango(sid, 0, 1, 0, n_cols),
            "cell": {"userEnteredFormat": {
                "backgroundColor": AZUL_OSCURO,
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
                "textFormat": {"bold": True, "foregroundColor": BLANCO, "fontSize": 11}}},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,"
                      "verticalAlignment,wrapStrategy,textFormat)"}},
        # Cuerpo centrado
        {"repeatCell": {
            "range": cuerpo,
            "cell": {"userEnteredFormat": {
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}},
            "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)"}},
        # Encabezado fijo, columnas fijas y sin líneas de cuadrícula
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {
                "frozenRowCount": 1, "frozenColumnCount": fmt.columnas_fijas,
                "hideGridlines": True}},
            "fields": "gridProperties(frozenRowCount,frozenColumnCount,hideGridlines)"}},
        # Filas alternadas
        {"addBanding": {"bandedRange": {
            "range": cuerpo,
            "rowProperties": {"firstBandColor": BLANCO, "secondBandColor": AZUL_CLARO}}}},
        # Filtros en el encabezado
        {"setBasicFilter": {"filter": {"range": _rango(sid, 0, n_filas, 0, n_cols)}}},
        # Alto del encabezado y ancho de las columnas
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 48}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": n_cols},
            "properties": {"pixelSize": fmt.ancho_columna}, "fields": "pixelSize"}},
    ]

    for col, patron in fmt.formatos_numero.items():
        pedidos.append({"repeatCell": {
            "range": _rango(sid, 1, n_filas, col, col + 1),
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": patron}}},
            "fields": "userEnteredFormat.numberFormat"}})

    for col, color_max in fmt.gradientes.items():
        pedidos.append(_regla(sid, _rango(sid, 1, n_filas, col, col + 1), gradiente=color_max))

    for col, texto, color in fmt.textos_coloreados:
        pedidos.append(_regla(
            sid, _rango(sid, 1, n_filas, col, col + 1),
            condicion={"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": texto}]},
            formato={"backgroundColor": color}))

    for col in fmt.marcar_si_uno:
        pedidos.append(_regla(
            sid, _rango(sid, 1, n_filas, col, col + 1),
            condicion={"type": "NUMBER_EQ", "values": [{"userEnteredValue": "1"}]},
            formato={"backgroundColor": ALERTA_SUAVE}))

    if fmt.cursiva_hasta:
        # Importante: Google Sheets aplica solo la primera regla que se cumple en cada celda.
        # Por eso la cursiva se limita a columnas que no tienen degradé ni alertas.
        pedidos.append(_regla(
            sid, _rango(sid, 1, n_filas, 0, fmt.cursiva_hasta),
            condicion={"type": "CUSTOM_FORMULA",
                       "values": [{"userEnteredValue": '=$C2="pronostico"'}]},
            formato={"textFormat": {"italic": True, "foregroundColor": GRIS}}))

    return pedidos


# ------------------------------------------------------------- hojas

def _conectar(ruta_credenciales: Path, nombre_sheet: str) -> gspread.Spreadsheet:
    if not ruta_credenciales.exists():
        raise ErrorSheets(f"No encuentro el archivo de credenciales: {ruta_credenciales}")
    try:
        cliente = gspread.service_account(filename=str(ruta_credenciales))
        return cliente.open(nombre_sheet)
    except gspread.SpreadsheetNotFound as e:
        raise ErrorSheets(
            f"No encuentro el Sheet '{nombre_sheet}'. ¿Está compartido como Editor "
            "con el client_email de la cuenta de servicio?"
        ) from e
    except ValueError as e:
        raise ErrorSheets(f"El archivo de credenciales no es válido: {e}") from e


def _hoja_limpia(sh: gspread.Spreadsheet, nombre: str, filas: int, cols: int) -> gspread.Worksheet:
    """Crea la pestaña desde cero (sin formato viejo). Si existía, la reemplaza."""
    temporal = f"{nombre}_nueva"
    try:  # resto de una ejecución anterior que se cortó a la mitad
        sh.del_worksheet(sh.worksheet(temporal))
    except gspread.WorksheetNotFound:
        pass

    try:
        vieja = sh.worksheet(nombre)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=nombre, rows=filas, cols=cols)

    nueva = sh.add_worksheet(title=temporal, rows=filas, cols=cols)
    sh.del_worksheet(vieja)
    nueva.update_title(nombre)
    return nueva


def _publicar_tabla(sh: gspread.Spreadsheet, nombre: str, df: pd.DataFrame,
                    fmt: FormatoHoja, pie: tuple[str, ...] = ()) -> gspread.Worksheet:
    # Los valores vacíos (NaN) no se pueden enviar a Google: se reemplazan por texto vacío
    df = df.rename(columns=ENCABEZADOS)
    datos = [df.columns.tolist()] + df.astype(object).where(df.notna(), "").values.tolist()
    n_filas, n_cols = len(datos), len(datos[0])

    ws = _hoja_limpia(sh, nombre, n_filas + len(pie) + 2, n_cols)
    ws.update(values=datos, range_name="A1")

    pedidos = _pedidos_formato(ws.id, n_filas, n_cols, fmt)
    if pie:
        fila_pie = n_filas + 2  # una fila en blanco de separación
        ws.update(values=[[texto] for texto in pie], range_name=f"A{fila_pie}")
        pedidos.append({"repeatCell": {
            "range": _rango(ws.id, fila_pie - 1, fila_pie - 1 + len(pie), 0, 1),
            "cell": {"userEnteredFormat": {
                "textFormat": {"italic": True, "fontSize": 9, "foregroundColor": GRIS}}},
            "fields": "userEnteredFormat.textFormat"}})

    # El formato es cosmético: si falla, los datos igual quedaron cargados.
    try:
        sh.batch_update({"requests": pedidos})
    except gspread.exceptions.APIError as e:
        log.warning("'%s': los datos se cargaron, pero no se pudo aplicar el formato (%s)", nombre, e)
    return ws


def _ordenar_y_limpiar(sh: gspread.Spreadsheet, en_orden: list[gspread.Worksheet]) -> None:
    try:
        ids = {ws.id for ws in en_orden}
        for ws in sh.worksheets():
            vacia = not any(any(celda for celda in fila) for fila in ws.get_all_values())
            if ws.title in HOJAS_POR_DEFECTO and ws.id not in ids and vacia:
                sh.del_worksheet(ws)  # la hoja en blanco que trae todo Sheet nuevo
        sh.reorder_worksheets(en_orden)
    except gspread.exceptions.APIError as e:
        log.warning("No se pudo ordenar las pestañas (%s)", e)


def publicar_en_sheets(ruta_credenciales: Path, nombre_sheet: str,
                       diaria: pd.DataFrame, resumen: pd.DataFrame) -> None:
    """Publica dos pestañas: `resumen` (semáforo por ciudad) y `diario` (detalle)."""
    sh = _conectar(ruta_credenciales, nombre_sheet)
    ahora = datetime.now().strftime("%d-%m-%Y %H:%M")
    pie_resumen = (
        f"Actualizado: {ahora}",
        f"Semáforo según días de riesgo previstos: 🟢 0 · 🟡 {UMBRAL_RIESGO_MEDIO}-"
        f"{UMBRAL_RIESGO_ALTO - 1} · 🔴 {UMBRAL_RIESGO_ALTO} o más",
        "Fuente de datos: Open-Meteo.com (CC BY 4.0)",
    )
    try:
        ws_resumen = _publicar_tabla(sh, "resumen", resumen, FORMATO_RESUMEN, pie_resumen)
        ws_diario = _publicar_tabla(sh, "diario", diaria, FORMATO_DIARIO)
        _ordenar_y_limpiar(sh, [ws_resumen, ws_diario])
    except gspread.exceptions.APIError as e:
        raise ErrorSheets(
            f"Google respondió con un error: {e}. Revisá que Google Sheets API y Google "
            "Drive API estén activadas y que el Sheet esté compartido como Editor."
        ) from e