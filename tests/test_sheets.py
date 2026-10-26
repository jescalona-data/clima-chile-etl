"""Tests de sheets.py: formato y publicación, con un Google Sheets falso (sin internet)."""
import gspread
import pytest

from clima_etl.sheets import (
    ENCABEZADOS,
    FORMATO_DIARIO,
    FORMATO_RESUMEN,
    _pedidos_formato,
    _publicar_tabla,
)
from clima_etl.transform import COLUMNAS_DIARIAS, agregar_nivel_riesgo, resumen_por_ciudad


class HojaFalsa:
    def __init__(self):
        self.id = 7
        self.actualizaciones = []

    def update(self, values=None, range_name=None, **kwargs):
        self.actualizaciones.append((range_name, values))


class SheetFalso:
    def __init__(self, falla_el_formato=False):
        self.hoja = HojaFalsa()
        self.pedidos = []
        self.falla_el_formato = falla_el_formato

    def worksheet(self, nombre):
        raise gspread.WorksheetNotFound(nombre)

    def add_worksheet(self, title, rows, cols):
        return self.hoja

    def del_worksheet(self, hoja):
        pass

    def batch_update(self, cuerpo):
        if self.falla_el_formato:
            respuesta = type("R", (), {
                "status_code": 400, "text": "{}",
                "json": lambda self: {"error": {"code": 400, "message": "x", "status": "X"}},
            })()
            raise gspread.exceptions.APIError(respuesta)
        self.pedidos.append(cuerpo)


def test_hay_un_encabezado_legible_para_cada_columna(tabla_diaria, hoy):
    resumen = agregar_nivel_riesgo(resumen_por_ciudad(tabla_diaria, hoy))

    for columna in list(COLUMNAS_DIARIAS) + list(resumen.columns):
        assert columna in ENCABEZADOS, f"Falta el encabezado legible de '{columna}'"


def test_la_cursiva_de_pronostico_no_tapa_degrades_ni_alertas():
    """Regresión: Google Sheets aplica solo la PRIMERA regla que se cumple en cada celda.

    Una regla de cursiva sobre toda la tabla ocultaba los colores de las filas de
    pronóstico, justo donde más importa ver el riesgo.
    """
    pedidos = _pedidos_formato(sid=1, n_filas=38, n_cols=12, fmt=FORMATO_DIARIO)

    reglas = [p["addConditionalFormatRule"]["rule"] for p in pedidos
              if "addConditionalFormatRule" in p]
    cursiva = [r for r in reglas
               if r.get("booleanRule", {}).get("condition", {}).get("type") == "CUSTOM_FORMULA"]
    columnas_con_color = set(FORMATO_DIARIO.gradientes) | set(FORMATO_DIARIO.marcar_si_uno)

    assert len(cursiva) == 1
    assert cursiva[0]["ranges"][0]["endColumnIndex"] <= min(columnas_con_color)


@pytest.mark.parametrize("formato, n_cols", [(FORMATO_DIARIO, 12), (FORMATO_RESUMEN, 8)])
def test_el_formato_no_se_sale_de_la_tabla(formato, n_cols):
    pedidos = _pedidos_formato(sid=1, n_filas=10, n_cols=n_cols, fmt=formato)

    rangos = []
    for pedido in pedidos:
        for contenido in pedido.values():
            if "range" in contenido and "endColumnIndex" in contenido["range"]:
                rangos.append(contenido["range"])
            if "rule" in contenido:
                rangos.extend(contenido["rule"]["ranges"])

    assert rangos
    assert all(r["endColumnIndex"] <= n_cols for r in rangos)


def test_los_datos_faltantes_se_envian_como_texto_vacio(respuesta_api, hoy):
    """Regresión: Google rechaza NaN, porque no existe en JSON."""
    from clima_etl.sheets import FormatoHoja
    from clima_etl.transform import construir_tabla_diaria

    crudo = {"X": respuesta_api(["2026-10-19"], lluvia=[None])}
    tabla = construir_tabla_diaria(crudo, hoy, 10, 50)
    sheet = SheetFalso()

    _publicar_tabla(sheet, "diario", tabla, FormatoHoja())

    _, valores = sheet.hoja.actualizaciones[0]
    encabezado, fila = valores
    assert fila[encabezado.index("Lluvia (mm)")] == ""


def test_los_encabezados_del_sheet_son_legibles(tabla_diaria):
    from clima_etl.sheets import FormatoHoja

    sheet = SheetFalso()

    _publicar_tabla(sheet, "diario", tabla_diaria, FormatoHoja())

    encabezado = sheet.hoja.actualizaciones[0][1][0]
    assert "Viento máx (km/h)" in encabezado
    assert "viento_max_kmh" not in encabezado


def test_si_falla_el_formato_los_datos_igual_se_cargan(tabla_diaria):
    from clima_etl.sheets import FormatoHoja

    sheet = SheetFalso(falla_el_formato=True)

    hoja = _publicar_tabla(sheet, "diario", tabla_diaria, FormatoHoja())  # no debe lanzar error

    assert hoja is sheet.hoja
    assert len(sheet.hoja.actualizaciones) == 1
