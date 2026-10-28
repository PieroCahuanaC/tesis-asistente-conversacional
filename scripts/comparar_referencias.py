"""Ejecuta el SQL de referencia de cada investigador y compara ambos resultados (doble cálculo, 3.5.3).

Uso:  python scripts/comparar_referencias.py               (CIERRE el Excel antes de ejecutar)
      python scripts/comparar_referencias.py --archivo otra_ruta.xlsx

Por cada fila de la hoja Banco con SQL_Rodrigo y SQL_Tony:
  - ejecuta cada consulta con el rol de solo lectura (mismo validador que usa el asistente);
  - escribe el resultado en Resultado_Rodrigo / Resultado_Tony;
  - marca Coinciden = SÍ / NO según el criterio de la fila (tolerancia S/ 1 o 0,5 %; listas sin orden).
«NO RESPONDIBLE» en ambos SQL cuenta como coincidencia (preguntas T7).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import PatternFill  # noqa: E402

from asistente.config import RAIZ  # noqa: E402
from asistente.db.conexion import conectar_ro  # noqa: E402
from asistente.evaluacion.comparar import NO_RESPONDIBLE, resultados_equivalentes  # noqa: E402
from asistente.sql_guard.ejecutor import ejecutar  # noqa: E402

VERDE = PatternFill("solid", fgColor="C6EFCE")
ROJO = PatternFill("solid", fgColor="FFC7CE")
GRIS = PatternFill("solid", fgColor="E7E6E6")


def _correr(sql: str | None, conn):
    """Devuelve (texto para la celda, filas o NO_RESPONDIBLE o None)."""
    if sql is None or not str(sql).strip():
        return None, None
    if str(sql).strip().upper().rstrip(".") == NO_RESPONDIBLE:
        return NO_RESPONDIBLE, NO_RESPONDIBLE
    r = ejecutar(str(sql), conn)
    if not r.ok:
        return f"ERROR: {r.error}", None
    texto = json.dumps(r.filas, ensure_ascii=False, default=str)
    if r.truncado:
        texto += "  (truncado a 500 filas)"
    return texto[:32000], r.filas


def comparar_archivo(ruta: Path) -> dict:
    wb = load_workbook(ruta)
    ws = wb["Banco"]
    col = {c.value: c.column for c in ws[1]}
    conteo = {"comparadas": 0, "coinciden": 0, "no_coinciden": 0, "incompletas": 0}
    with conectar_ro() as conn:
        for fila in range(2, ws.max_row + 1):
            if not ws.cell(fila, col["Pregunta"]).value:
                continue
            criterio = ws.cell(fila, col["Criterio"]).value or "numerico"
            txt_r, res_r = _correr(ws.cell(fila, col["SQL_Rodrigo"]).value, conn)
            txt_t, res_t = _correr(ws.cell(fila, col["SQL_Tony"]).value, conn)
            ws.cell(fila, col["Resultado_Rodrigo"]).value = txt_r
            ws.cell(fila, col["Resultado_Tony"]).value = txt_t
            celda = ws.cell(fila, col["Coinciden"])
            if txt_r is None or txt_t is None:
                celda.value, celda.fill = None, GRIS
                conteo["incompletas"] += 1
                continue
            if res_r is None or res_t is None:          # alguno con error de SQL
                iguales = False
            elif NO_RESPONDIBLE in (res_r, res_t):
                iguales = res_r == res_t
            else:
                iguales = resultados_equivalentes(res_r, res_t, criterio)
            celda.value, celda.fill = ("SÍ", VERDE) if iguales else ("NO", ROJO)
            conteo["comparadas"] += 1
            conteo["coinciden" if iguales else "no_coinciden"] += 1
    try:
        wb.save(ruta)
    except PermissionError:
        sys.exit(f"No se pudo guardar {ruta.name}: ciérrelo en Excel y vuelva a ejecutar el script.")
    return conteo


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archivo", type=Path, default=RAIZ / "eval" / "banco" / "banco_preguntas.xlsx")
    args = p.parse_args()
    c = comparar_archivo(args.archivo)
    print(f"Preguntas comparadas: {c['comparadas']}  |  coinciden: {c['coinciden']}  |  "
          f"no coinciden: {c['no_coinciden']}  |  sin los dos SQL todavía: {c['incompletas']}")
    if c["no_coinciden"]:
        print("Revisen juntos las filas marcadas NO (en rojo) en la hoja Banco.")


if __name__ == "__main__":
    main()
