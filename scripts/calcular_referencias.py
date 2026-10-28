"""Llena el solucionario del banco de preguntas con el doble cálculo A/B (sección 3.5.3).

Uso:  python scripts/calcular_referencias.py            (CIERRE el Excel antes de ejecutar)
      python scripts/calcular_referencias.py --archivo otra_ruta.xlsx

  Cálculo A: SQL de referencia por pregunta, ejecutado con el rol de solo lectura sobre la base integrada.
  Cálculo B: Python (pandas) directamente sobre los .xls del PTE y los CSV del MEF, sin la base.
  Si A y B coinciden (tolerancia S/ 1 o 0,5 %; listas sin orden) el resultado pasa a Valor_referencia.
  Además sortea (semilla del estudio) el 20 % de preguntas que cada investigador verifica a mano.

Ninguno de los dos cálculos usa las herramientas ni el orquestador del asistente.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402

from asistente.config import RAIZ, ajustes, commit_actual  # noqa: E402
from asistente.db.conexion import conectar_ro  # noqa: E402
from asistente.evaluacion import calculo_a as A  # noqa: E402
from asistente.evaluacion import calculo_b as B  # noqa: E402
from asistente.evaluacion.comparar import NO_RESPONDIBLE, resultados_equivalentes  # noqa: E402
from asistente.evaluacion.familias import INTERPRETACION, clasificar  # noqa: E402
from asistente.evaluacion.guia_verificacion import PREPARACION, pasos  # noqa: E402
from asistente.sql_guard.ejecutor import ejecutar  # noqa: E402

VERDE = PatternFill("solid", fgColor="C6EFCE")
ROJO = PatternFill("solid", fgColor="FFC7CE")
GRIS = PatternFill("solid", fgColor="E7E6E6")
AMARILLO = PatternFill("solid", fgColor="FFF2CC")
RENOMBRAR = {"SQL_Rodrigo": "SQL_A", "SQL_Tony": "Calculo_B", "Resultado_Rodrigo": "Resultado_A",
             "Resultado_Tony": "Resultado_B"}
NUEVAS = [("Familia", 20), ("Verifica", 11)]
INVESTIGADORES = ["Rodrigo", "Tony"]
TRAMO_ESTADO = "Entre 2024-08 y 2025-03 el estado de las órdenes no está actualizado en el PTE: solo se excluyen las anuladas que figuran como tales."
FAMILIAS_MONTO_ORDENES = {"monto_periodo", "ordenes_periodo", "promedio", "comp_tipo_monto", "max_orden", "top_ordenes"}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def resolver_nombre_sql(nombre: str, anio: int, conn) -> tuple[str, str]:
    """Cálculo A: busca la finalidad por su nombre con SQL. Devuelve (código, SQL usado)."""
    q = ("SELECT DISTINCT finalidad FROM datos.ejecucion_presupuestal WHERE anio = %d AND "
         "translate(lower(nombre_meta), 'áéíóúü', 'aeiouu') LIKE '%%%s%%'" % (anio, _sin_tildes(nombre).replace("'", "''")))
    r = ejecutar(q, conn)
    if not r.ok or len(r.filas) != 1:
        raise ValueError(f"Cálculo A: «{nombre}» en {anio} no identifica una única finalidad ({r.filas if r.ok else r.error})")
    return r.filas[0][0], q


def _toca_tramo(p: dict) -> bool:
    a = p.get("anio")
    m1, m2 = p.get("m1", p.get("mes", 1)), p.get("m2", p.get("mes", 12))
    return any((a == 2024 and m >= 8) or (a == 2025 and m <= 3) for m in range(m1, m2 + 1))


def _json(filas) -> str:
    return json.dumps(filas, ensure_ascii=False, default=float)


def _descripcion_b(fam) -> str:
    params = ", ".join(f"{k}={v}" for k, v in fam.p.items())
    return f"calculo_b.calcular · familia={fam.nombre} · {params}"


def sortear_verificacion(filas: list[dict], semilla: int) -> dict[str, str]:
    """20 % de las preguntas, estratificado por tipo (T1..T7), repartido en partes iguales."""
    por_tipo = defaultdict(list)
    for f in filas:
        por_tipo[f["Tipo"]].append(f["ID"])
    rng = random.Random(semilla)
    elegidas = []
    for tipo in sorted(por_tipo):
        ids = sorted(por_tipo[tipo])
        elegidas += rng.sample(ids, max(1, round(0.2 * len(ids))))
    rng.shuffle(elegidas)
    return {pid: INVESTIGADORES[i % 2] for i, pid in enumerate(elegidas)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archivo", default=str(RAIZ / "eval" / "banco" / "banco_preguntas.xlsx"))
    args = ap.parse_args()
    wb = load_workbook(args.archivo)
    ws = wb["Banco"]

    cab = {c.value: c.column for c in ws[1]}
    for viejo, nuevo in RENOMBRAR.items():
        if viejo in cab:
            ws.cell(1, cab.pop(viejo), nuevo)
    cab = {c.value: c.column for c in ws[1]}
    if "Verificacion_manual" in cab:          # versión anterior: la verificación pasa a su propia hoja
        ws.delete_cols(cab["Verificacion_manual"])
    cab = {c.value: c.column for c in ws[1]}
    col_sig = ws.max_column + 1
    for nombre, ancho in NUEVAS:
        if nombre not in cab:
            ws.cell(1, col_sig, nombre).font = Font(bold=True)
            ws.column_dimensions[ws.cell(1, col_sig).column_letter].width = ancho
            cab[nombre] = col_sig
            col_sig += 1

    filas = [{k: ws.cell(r, c).value for k, c in cab.items()} | {"_r": r}
             for r in range(2, ws.max_row + 1) if ws.cell(r, cab["ID"]).value]
    asignacion = sortear_verificacion(filas, ajustes()["llm"]["semilla"])

    resumen = defaultdict(int)
    a_verificar = []
    with conectar_ro() as conn:
        for f in filas:
            r = f["_r"]
            fam = clasificar(f["Pregunta"], f["Tipo"], f["Criterio"])
            obs = [INTERPRETACION[fam.nombre]]
            celdas = {"Familia": fam.nombre, "Verifica": asignacion.get(f["ID"], "")}
            if fam.nombre == "no_respondible":
                celdas |= {"SQL_A": NO_RESPONDIBLE, "Calculo_B": NO_RESPONDIBLE, "Resultado_A": NO_RESPONDIBLE,
                           "Resultado_B": NO_RESPONDIBLE, "Coinciden": "SÍ", "Valor_referencia": NO_RESPONDIBLE}
                resumen["no_respondible"] += 1
            else:
                prefijo = ""
                if "nombre" in fam.p:
                    anio = fam.p.get("anio") or fam.p.get("a1")
                    cod_a, q_nombre = resolver_nombre_sql(fam.p["nombre"], anio, conn)
                    cod_b = B.resolver_nombre(fam.p["nombre"], anio)
                    if cod_a != cod_b:
                        raise SystemExit(f"{f['ID']}: A resuelve {cod_a} y B {cod_b}")
                    fam.p["fin"] = cod_a
                    prefijo = f"-- paso 1: «{fam.p['nombre']}» → finalidad {cod_a}\n-- {q_nombre}\n-- paso 2:\n"
                    obs.append(f"«{fam.p['nombre']}» corresponde a la finalidad {cod_a}.")
                sql = A.sql(fam)
                ra = ejecutar(sql, conn)
                if not ra.ok:
                    raise SystemExit(f"{f['ID']}: el SQL A falló: {ra.error}\n{sql}")
                rb = B.calcular(fam)
                iguales = resultados_equivalentes(ra.filas, rb, f["Criterio"])
                celdas |= {"SQL_A": prefijo + sql, "Calculo_B": _descripcion_b(fam), "Resultado_A": _json(ra.filas),
                           "Resultado_B": _json(rb), "Coinciden": "SÍ" if iguales else "NO",
                           "Valor_referencia": _json(rb) if iguales else None}
                if fam.nombre in FAMILIAS_MONTO_ORDENES and _toca_tramo(fam.p):
                    obs.append(TRAMO_ESTADO)
                resumen["coinciden" if iguales else "difieren"] += 1
            celdas["Observaciones"] = " ".join(obs)
            for k, v in celdas.items():
                c = ws.cell(r, cab[k], v)
                c.alignment = Alignment(wrap_text=True, vertical="top")
                if k in ("Resultado_A", "Resultado_B", "Familia"):
                    c.fill = GRIS
            ws.cell(r, cab["Coinciden"]).fill = VERDE if celdas["Coinciden"] == "SÍ" else ROJO
            if celdas["Verifica"]:
                origen, guia = pasos(fam)
                a_verificar.append([f["ID"], celdas["Verifica"], f["Pregunta"], origen, guia, celdas["Valor_referencia"],
                                    celdas["Observaciones"]])

    _hoja_verificacion(wb, sorted(a_verificar, key=lambda x: (x[1], x[0])))
    _instrucciones(wb, commit_actual())
    wb.save(args.archivo)
    n_v = {i: sum(1 for v in asignacion.values() if v == i) for i in INVESTIGADORES}
    print(f"Coinciden: {resumen['coinciden']} · difieren: {resumen['difieren']} · no respondibles: {resumen['no_respondible']}")
    print(f"Verificación manual: {n_v}")
    return 1 if resumen["difieren"] else 0


def _hoja_verificacion(wb, filas: list[list]) -> None:
    """Hoja para la verificación manual del 20 % (lo que ya hayan anotado se conserva)."""
    from openpyxl.worksheet.datavalidation import DataValidation
    previo = {}
    if "Verificacion" in wb.sheetnames:
        v = wb["Verificacion"]
        h = {c.value: c.column for c in v[len(PREPARACION) + 2]}
        if "ID" in h:
            for r in range(len(PREPARACION) + 3, v.max_row + 1):
                pid = v.cell(r, h["ID"]).value
                if pid:
                    previo[pid] = [v.cell(r, h[k]).value for k in ("Valor_encontrado", "Resultado", "Comentario")]
        del wb["Verificacion"]
    v = wb.create_sheet("Verificacion", 1)
    for i, t in enumerate(PREPARACION, start=1):
        v.cell(i, 1, t).font = Font(bold=t.isupper() and bool(t))
    fila_cab = len(PREPARACION) + 2
    cab = ["ID", "Verifica", "Pregunta", "Archivo", "Pasos", "Valor_referencia", "Interpretación",
           "Valor_encontrado", "Resultado", "Comentario"]
    anchos = [7, 10, 45, 34, 70, 26, 40, 22, 13, 35]
    for j, (c, a) in enumerate(zip(cab, anchos), start=1):
        v.cell(fila_cab, j, c).font = Font(bold=True)
        v.column_dimensions[v.cell(fila_cab, j).column_letter].width = a
    dv = DataValidation(type="list", formula1='"conforme,observada"', allow_blank=True)
    v.add_data_validation(dv)
    for i, fila in enumerate(filas, start=fila_cab + 1):
        for j, x in enumerate(fila + previo.get(fila[0], [None, None, None]), start=1):
            c = v.cell(i, j, x)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if j >= 8:
                c.fill = AMARILLO
        dv.add(v.cell(i, 9))
    v.freeze_panes = v.cell(fila_cab + 1, 3)
    v.auto_filter.ref = f"A{fila_cab}:J{fila_cab + len(filas)}"


def _instrucciones(wb, commit: str) -> None:
    ws = wb["Instrucciones"]
    ws.delete_rows(1, ws.max_row)
    texto = [
        "Banco de preguntas para evaluar el asistente (sección 3.4 y Anexo 5)",
        "",
        "Solucionario por doble cálculo independiente (sección 3.5.3)",
        "1. Cálculo A (columna SQL_A): una consulta SQL por pregunta sobre la base integrada, ejecutada con el rol de solo lectura.",
        "2. Cálculo B (columna Calculo_B): un programa en Python que lee directamente los .xls del PTE y los CSV del MEF, sin pasar por la base.",
        "3. Coinciden = SÍ cuando A y B dan lo mismo (tolerancia S/ 1 o 0,5 %; listas sin importar el orden). Solo entonces se llena Valor_referencia.",
        "4. Observaciones explica exactamente qué se calculó (qué se suma, qué se excluye). Si no están de acuerdo con una interpretación, anótenlo en la hoja Verificacion.",
        "5. Verificación humana: hoja Verificacion. Cada investigador revisa a mano, en Excel y con los archivos originales, las preguntas con su nombre (20 % sorteado y estratificado por tipo).",
        "6. Juicio de expertos (Anexo 4) sobre las preguntas; luego se congela el conjunto de prueba y ya no se modifica.",
        "",
        "Para regenerar: python scripts/calcular_referencias.py (con este archivo CERRADO).",
        f"Generado con el commit {commit}.",
        "",
        "Leyenda de colores",
        "Verde/rojo: Coinciden.   Gris: lo llena el script (no editar).   Amarillo: lo llenan ustedes (hoja Verificacion).",
        "",
        "Reglas",
        "- NUNCA calcular el solucionario con las herramientas del asistente: sería corregir el examen con las respuestas del alumno.",
        "- Saldo al cierre del mes m = PIM del año − certificación acumulada de enero a m (D13). Gasto = devengado.",
        "- Órdenes: se cuentan las anuladas; los montos las excluyen (D9).",
        "- Entre 2024-08 y 2025-03 las órdenes no tienen código de finalidad ni estado confiable: consultas de órdenes por meta o por estado en esos meses son NO RESPONDIBLES.",
        "- NO RESPONDIBLE: la respuesta correcta del asistente es abstenerse sin dar cifras.",
    ]
    for i, t in enumerate(texto, start=1):
        ws.cell(i, 1, t)
    ws.cell(1, 1).font = Font(bold=True, size=13)
    for i in (3, 15, 18):
        ws.cell(i, 1).font = Font(bold=True)


if __name__ == "__main__":
    raise SystemExit(main())
