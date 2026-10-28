"""Genera la plantilla del banco de preguntas (eval/banco/banco_preguntas.xlsx) con 60 preguntas
CANDIDATAS construidas a partir de los datos reales (metas, meses y montos que existen).

Uso:  python scripts/generar_banco.py            (no sobrescribe un banco existente)
      python scripts/generar_banco.py --forzar   (lo regenera: ¡se pierde lo escrito en él!)

Las candidatas son un punto de partida: los investigadores las revisan, corrigen o descartan y
escriben las que faltan hasta 230. El script NO calcula respuestas: el solucionario lo escribe cada
investigador con su propio SQL (cálculo independiente, sección 3.5.3) y se compara con
scripts/comparar_referencias.py. La selección es reproducible (semilla fija).
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import Workbook  # noqa: E402
from openpyxl.comments import Comment  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

from asistente.config import RAIZ, ajustes  # noqa: E402
from asistente.db.conexion import conectar_admin, conectar_ro  # noqa: E402
from asistente.orquestador import describir_esquema  # noqa: E402

SEMILLA = 20251231
SALIDA = RAIZ / "eval" / "banco" / "banco_preguntas.xlsx"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre",
         "octubre", "noviembre", "diciembre"]
TRIM = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto"}
METAS_TABLA4 = {"T1": 40, "T2": 40, "T3": 33, "T4": 27, "T5": 20, "T6": 20, "T7": 20}
COLUMNAS = ["ID", "Conjunto", "Tipo", "Dificultad", "Criterio", "Pregunta", "Origen", "SQL_Rodrigo",
            "SQL_Tony", "Resultado_Rodrigo", "Resultado_Tony", "Coinciden", "Valor_referencia", "Observaciones"]
ANCHOS = [7, 12, 7, 13, 12, 60, 14, 45, 45, 30, 30, 11, 30, 30]


def _soles(x: float) -> str:
    return f"S/ {x:,.0f}".replace(",", " ")


class Datos:
    """Lecturas de apoyo para elegir parámetros realistas (no son respuestas de referencia)."""

    def __init__(self, conn):
        self.c = conn
        self.tramo = ajustes()["tramo_sin_codigo_ni_estado"]

    def q(self, sql, p=None):
        return self.c.execute(sql, p).fetchall()

    def metas(self, anio, pim_min=50_000):
        return self.q("SELECT finalidad, nombre_meta FROM datos.v_finalidad_mes WHERE anio = %s AND mes = 12 "
                      "AND pim >= %s ORDER BY finalidad", (anio, pim_min))

    def metas_con_nombre_unico(self, anio):
        """Actividades de nombre corto que no se confunden con otra finalidad del mismo año."""
        filas = self.q("SELECT DISTINCT finalidad, nombre_meta FROM datos.v_finalidad_mes "
                       "WHERE anio = %s AND pim >= 100000 AND length(nombre_meta) <= 45", (anio,))
        todos = [n.upper() for _, n in self.q("SELECT DISTINCT finalidad, nombre_meta FROM datos.v_finalidad_mes "
                                              "WHERE anio = %s", (anio,))]
        return [(f, n) for f, n in filas if sum(n.upper() in t for t in todos) == 1]

    def en_tramo(self, anio, mes):
        return self.tramo["desde"] <= f"{anio}-{mes:02d}" <= self.tramo["hasta"]

    def saldo(self, fin, anio, mes):
        return float(self.q("SELECT saldo FROM datos.v_finalidad_mes WHERE finalidad = %s AND anio = %s "
                            "AND mes = %s", (fin, anio, mes))[0][0])

    def alertas(self, anio, mes, umbral):
        return self.q("SELECT count(*) FROM datos.v_finalidad_mes WHERE anio = %s AND mes = %s AND pim > 0 "
                      "AND avance_devengado_pct > %s", (anio, mes, umbral))[0][0]


def candidatas(d: Datos, rnd: random.Random) -> list[dict]:
    out = []
    usadas: set[str] = set()

    def add(tipo, dificultad, criterio, texto):
        if texto in usadas:
            return False
        usadas.add(texto)
        out.append({"Tipo": tipo, "Dificultad": dificultad, "Criterio": criterio, "Pregunta": texto,
                    "Origen": "candidata"})
        return True

    def elegir_meta(fuente, ya: set):
        libres = [m for m in fuente if m[0] not in ya]
        m = rnd.choice(libres or fuente)
        ya.add(m[0])
        return m

    def mes_fuera_tramo(anio, lo=1, hi=12):
        while True:
            m = rnd.randint(lo, hi)
            if not d.en_tramo(anio, m):
                return m

    nombre = lambda n: n.lower()  # noqa: E731

    # ---- T1 disponibilidad por meta (12)
    vistas: set[str] = set()
    for i in range(8):
        anio = (2023, 2024, 2025)[i % 3]
        fin, _n = elegir_meta(d.metas(anio), vistas)
        mes = rnd.randint(1, 11)
        add("T1", "simple", "numerico",
            rnd.choice([f"¿Cuál es el saldo disponible (PIM menos certificación) de la meta {fin} al cierre de {MESES[mes - 1]} de {anio}?",
                        f"¿Cuánto saldo le quedaba a la meta {fin} a fines de {MESES[mes - 1]} de {anio}?"]))
    for i in range(4):
        anio = (2025, 2024, 2023, 2025)[i]
        fin, n = elegir_meta(d.metas_con_nombre_unico(anio), vistas)
        mes = rnd.randint(2, 11)
        add("T1", "varios_pasos", "numerico",
            f"¿Cuánto saldo presupuestal tenía la meta de {nombre(n)} al cierre de {MESES[mes - 1]} de {anio}?")

    # ---- T2 ejecución por meta y periodo (12)
    for _ in range(4):
        anio = rnd.choice([2023, 2024, 2025])
        fin, _n = rnd.choice(d.metas(anio))
        m1 = rnd.randint(1, 9)
        m2 = rnd.randint(m1 + 1, min(m1 + 4, 12))
        add("T2", "agregacion", "numerico",
            f"¿Cuánto se devengó en la meta {fin} entre {MESES[m1 - 1]} y {MESES[m2 - 1]} de {anio}?")
    for _ in range(3):
        anio = rnd.choice([2023, 2024, 2025])
        fin, n = rnd.choice(d.metas_con_nombre_unico(anio))
        t = rnd.randint(1, 4)
        add("T2", "varios_pasos", "numerico",
            f"¿Cuánto se comprometió en {nombre(n)} en el {TRIM[t]} trimestre de {anio}?")
    for _ in range(3):
        anio = rnd.choice([2023, 2024, 2025])
        mes = rnd.randint(1, 12)
        add("T2", "simple", "numerico",
            f"¿Cuánto devengó en total la municipalidad en {MESES[mes - 1]} de {anio}?")
    for _ in range(2):
        anio = rnd.choice([2023, 2024, 2025])
        fin, _n = rnd.choice(d.metas(anio))
        add("T2", "agregacion", "numerico",
            f"¿Cuál fue el devengado acumulado de la meta {fin} al cierre de {anio} y qué porcentaje de su PIM representa?")

    # ---- T3 agregados de órdenes (10)
    for _ in range(4):
        anio = rnd.choice([2023, 2024, 2025])
        mes = mes_fuera_tramo(anio)
        tipo = rnd.choice([("órdenes de servicio", "O/S"), ("órdenes de compra", "O/C")])[0]
        add("T3", "agregacion", "numerico",
            f"¿Cuántas {tipo} menores o iguales a 8 UIT se emitieron en {MESES[mes - 1]} de {anio} y por qué monto total?")
    for anio in rnd.sample([2023, 2024, 2025], 2):
        add("T3", "simple", "numerico", f"¿Cuántas órdenes de compra menores o iguales a 8 UIT se emitieron en {anio}?")
    for _ in range(2):
        anio = rnd.choice([2023, 2025])
        mes = mes_fuera_tramo(anio, 4 if anio == 2025 else 1, 12)
        fin = rnd.choice(["0000888", "0006508"])
        add("T3", "agregacion", "numerico",
            f"¿Cuál fue el monto total de las órdenes menores o iguales a 8 UIT de la meta {fin} emitidas en {MESES[mes - 1]} de {anio}?")
    add("T3", "simple", "numerico", "¿Cuántas órdenes menores o iguales a 8 UIT fueron anuladas en 2023?")
    add("T3", "agregacion", "numerico",
        "¿Cuántas órdenes menores o iguales a 8 UIT se emitieron en el primer semestre de 2023 y por qué monto total?")

    # ---- T4 rankings y comparaciones (8)
    for anio in (2023, 2025):
        add("T4", "agregacion", "lista", f"¿Qué cinco metas concentraron más gasto devengado en {anio}?")
    add("T4", "agregacion", "lista", "¿Cuáles fueron las tres metas con mayor PIM en 2024?")
    for _ in range(2):
        fin, _n = rnd.choice([m for m in d.metas(2023) if m in d.metas(2024)])
        add("T4", "varios_pasos", "numerico",
            f"¿Cómo varió el devengado anual de la meta {fin} entre 2023 y 2024 (en soles y en porcentaje)?")
    add("T4", "agregacion", "numerico", "¿En qué mes de 2023 se emitieron más órdenes de servicio menores o iguales a 8 UIT y cuántas fueron?")
    add("T4", "agregacion", "lista", "¿Qué tres metas concentraron el mayor monto en órdenes menores o iguales a 8 UIT en 2023?")
    add("T4", "varios_pasos", "numerico", "¿En cuánto cambió el PIM total de la municipalidad de 2024 a 2025?")

    # ---- T5 alertas por umbral (6): umbrales que dejen listas de 2 a 12 metas
    # Con el PIM de fin de año (D13) muchas metas pequeñas llegan pronto al 100 %: las preguntas de
    # lista se limitan a combinaciones con 2 a 12 metas; el resto se plantea como conteo.
    combos = [(a, m, u) for a in (2023, 2024, 2025) for m in range(1, 11) for u in (50, 60, 70, 80, 90, 95)]
    cortas = [c for c in combos if 2 <= d.alertas(*c) <= 12]
    largas = [c for c in combos if d.alertas(*c) > 12 and c[0] != 2023]
    for anio, mes, u in rnd.sample(cortas, 4):
        add("T5", "agregacion", "lista",
            f"¿Qué metas superan el {u} % de ejecución (devengado) de su PIM al cierre de {MESES[mes - 1]} de {anio}?")
    for anio, mes, u in rnd.sample(largas, 2):
        add("T5", "agregacion", "numerico",
            f"¿Cuántas metas tenían un avance de ejecución mayor al {u} % de su PIM al cierre de {MESES[mes - 1]} de {anio}?")

    # ---- T6 validación previa (6): montos por encima y por debajo del saldo
    factores = [0.4, 0.8, 1.2, 1.6, 0.6, 1.4]
    vistas6: set[str] = set()
    for i, f in enumerate(factores):
        for _intento in range(200):
            anio = (2023, 2024, 2025)[i % 3]
            mes = rnd.randint(3, 10)
            fuente = d.metas_con_nombre_unico(anio) if i >= 4 else d.metas(anio)
            fin, n = elegir_meta(fuente, vistas6)
            s = d.saldo(fin, anio, mes)
            if s > 5000:
                break
        else:
            raise RuntimeError("No se encontró una meta con saldo para T6")
        monto = max(500, round(s * f / 500) * 500)
        sujeto = f"la meta de {nombre(n)}" if i >= 4 else f"la meta {fin}"
        add("T6", "varios_pasos", "numerico",
            f"¿Alcanza el saldo de {sujeto} para un requerimiento de {_soles(monto)} en {MESES[mes - 1]} de {anio}?")

    # ---- T7 no respondibles (6)
    os_ene25 = d.q("SELECT numero_orden FROM datos.orden WHERE tipo_orden = 'O/S' AND anio = 2025 AND mes = 1 "
                   "ORDER BY numero_orden LIMIT 1 OFFSET 20")[0][0]
    os_23 = d.q("SELECT numero_orden FROM datos.orden WHERE tipo_orden = 'O/S' AND anio = 2023 AND persona_natural "
                "ORDER BY numero_orden LIMIT 1 OFFSET 40")[0][0]
    for texto in [
        "¿Cuánto se gastará en la meta 0006508 en diciembre de 2026?",
        "¿Cuál era el saldo de la meta 0000888 al cierre de marzo de 2022?",
        f"¿A qué meta corresponde la orden de servicio {os_ene25} de enero de 2025?",
        "¿Cuánto se gastó en órdenes menores o iguales a 8 UIT de la meta 0000888 en octubre de 2024?",
        "¿Cuántas órdenes de servicio se anularon en noviembre de 2024?",
        f"¿Cuál es el nombre del proveedor de la orden de servicio {os_23} de 2023?",
    ]:
        add("T7", "simple", "abstencion", texto)
    return out


def escribir_excel(filas: list[dict], esquema: str) -> None:
    fuente = Font(name="Arial", size=10)
    negrita = Font(name="Arial", size=10, bold=True)
    titulo = Font(name="Arial", size=13, bold=True)
    blanco = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    cab = PatternFill("solid", fgColor="1F4E78")
    entrada = PatternFill("solid", fgColor="FFF2CC")   # celdas que llenan los investigadores
    auto = PatternFill("solid", fgColor="E7E6E6")      # celdas que llena el script de comparación
    borde = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
    ajuste = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    # ---------------- Instrucciones
    ws = wb.active
    ws.title = "Instrucciones"
    lineas = [
        ("Banco de preguntas para evaluar el asistente (sección 3.4 y Anexo 5)", titulo),
        ("", None),
        ("Qué es: el «examen» que se aplicará a C1, C2 y C3, con su solucionario.", negrita),
        ("1. Completar 230 preguntas en la hoja Banco: 200 de PRUEBA (distribuidas como en la hoja Distribucion) y 30 de DESARROLLO.", None),
        ("2. Las filas P001-P060 traen preguntas CANDIDATAS generadas desde los datos reales: revísenlas, corrijan la redacción o reemplácenlas. Cambien Origen a «propia» o «entrevista» cuando corresponda.", None),
        ("3. Cada investigador escribe SU PROPIO SQL (columnas SQL_Rodrigo y SQL_Tony) sin mirar el del otro. Pueden usar la hoja Esquema y probar en pgAdmin.", None),
        ("4. Para preguntas que no se pueden responder (T7), escriban NO RESPONDIBLE en lugar del SQL.", None),
        ("5. Ejecuten: python scripts/comparar_referencias.py  (con este archivo CERRADO). Llena Resultado_Rodrigo, Resultado_Tony y Coinciden.", None),
        ("6. Si Coinciden = NO, revisen juntos y corrijan el SQL equivocado. Cuando coincidan, escriban la respuesta acordada en Valor_referencia.", None),
        ("7. Juicio de expertos (Anexo 4) sobre las preguntas; luego se congela el conjunto de prueba y ya no se modifica.", None),
        ("", None),
        ("Leyenda de colores", negrita),
        ("Amarillo: celdas que llenan ustedes.   Gris: celdas que llena el script de comparación (no editar).", None),
        ("", None),
        ("Reglas", negrita),
        ("- NUNCA calcular el solucionario con las herramientas del asistente: sería corregir el examen con las respuestas del alumno.", None),
        ("- Una respuesta numérica es correcta si coincide con la referencia con tolerancia de S/ 1 o 0,5 %; una lista, si tiene exactamente los mismos elementos.", None),
        ("- Saldo al cierre del mes m = PIM del año - certificación acumulada de enero a m (decisión D13). Gasto = devengado.", None),
        ("- Entre 2024-08 y 2025-03 las órdenes no tienen código de finalidad ni estado confiable: consultas de órdenes por meta o por estado en esos meses son NO RESPONDIBLES.", None),
        ("- Dificultad: simple (un dato), agregacion (sumar/contar/listar), varios_pasos (buscar la meta por nombre, comparar periodos, evaluar un monto).", None),
        ("", None),
        ("Ejemplo de fila completa (formato esperado)", negrita),
        ("Pregunta: ¿Cuál es el saldo de la meta 0006508 al cierre de junio de 2025?   Tipo: T1   Dificultad: simple   Criterio: numerico", None),
        ("SQL: SELECT sum(pim) - (SELECT sum(certificado) FROM datos.ejecucion_presupuestal WHERE finalidad='0006508' AND anio=2025 AND mes BETWEEN 1 AND 6) FROM datos.ejecucion_presupuestal WHERE finalidad='0006508' AND anio=2025", None),
        ("Valor_referencia: 1452526.89", None),
    ]
    for i, (texto, f) in enumerate(lineas, start=1):
        c = ws.cell(row=i, column=1, value=texto)
        c.font = f or fuente
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 150

    # ---------------- Banco
    wb_b = wb.create_sheet("Banco")
    for j, (nom, ancho) in enumerate(zip(COLUMNAS, ANCHOS), start=1):
        c = wb_b.cell(row=1, column=j, value=nom)
        c.font, c.fill, c.alignment, c.border = blanco, cab, Alignment(wrap_text=True, vertical="center"), borde
        wb_b.column_dimensions[c.column_letter].width = ancho
    wb_b.freeze_panes = "B2"
    for i in range(230):
        r = i + 2
        fila = filas[i] if i < len(filas) else {}
        valores = {"ID": f"P{i + 1:03d}", **fila}
        for j, nom in enumerate(COLUMNAS, start=1):
            c = wb_b.cell(row=r, column=j, value=valores.get(nom))
            c.font, c.alignment, c.border = fuente, ajuste, borde
            if nom in ("Resultado_Rodrigo", "Resultado_Tony", "Coinciden"):
                c.fill = auto
            elif nom != "ID":
                c.fill = entrada
    wb_b["J1"].comment = Comment("Lo llena scripts/comparar_referencias.py", "generar_banco")
    listas = {"B": '"desarrollo,prueba"', "C": '"T1,T2,T3,T4,T5,T6,T7"', "D": '"simple,agregacion,varios_pasos"',
              "E": '"numerico,lista,abstencion"', "G": '"candidata,propia,entrevista"'}
    for col, opciones in listas.items():
        dv = DataValidation(type="list", formula1=opciones, allow_blank=True)
        wb_b.add_data_validation(dv)
        dv.add(f"{col}2:{col}231")

    # ---------------- Distribucion (fórmulas)
    wd = wb.create_sheet("Distribucion")
    encabezado = ["Tipo", "Meta (prueba, Tabla 4)", "Prueba en el banco", "Faltan (prueba)", "Desarrollo en el banco"]
    for j, t in enumerate(encabezado, start=1):
        c = wd.cell(row=1, column=j, value=t)
        c.font, c.fill, c.border = blanco, cab, borde
        wd.column_dimensions[c.column_letter].width = 24
    for i, (tipo, meta) in enumerate(METAS_TABLA4.items(), start=2):
        wd.cell(row=i, column=1, value=tipo)
        wd.cell(row=i, column=2, value=meta)
        wd.cell(row=i, column=3, value=f'=COUNTIFS(Banco!$C$2:$C$231,A{i},Banco!$B$2:$B$231,"prueba")')
        wd.cell(row=i, column=4, value=f"=MAX(0,B{i}-C{i})")
        wd.cell(row=i, column=5, value=f'=COUNTIFS(Banco!$C$2:$C$231,A{i},Banco!$B$2:$B$231,"desarrollo")')
    total = len(METAS_TABLA4) + 2
    wd.cell(row=total, column=1, value="Total")
    for col in "BCDE":
        wd[f"{col}{total}"] = f"=SUM({col}2:{col}{total - 1})"
    wd.cell(row=total + 1, column=1, value="Meta de desarrollo")
    wd.cell(row=total + 1, column=5, value=30)
    wd.cell(row=total + 2, column=1, value="Fuente de las metas: Tabla 4 de la tesis (200 de prueba) y sección 3.4 (30 de desarrollo).")
    for fila in wd.iter_rows(min_row=1, max_row=total + 2):
        for c in fila:
            if c.font != blanco:
                c.font = negrita if c.row == total else fuente

    # ---------------- Esquema
    we = wb.create_sheet("Esquema")
    we.column_dimensions["A"].width = 160
    we.cell(row=1, column=1, value="Tablas y vistas del esquema datos (para escribir el SQL de referencia)").font = titulo
    for i, linea in enumerate(esquema.splitlines(), start=3):
        c = we.cell(row=i, column=1, value=linea)
        c.font = Font(name="Courier New", size=9, bold=not linea.startswith("  "))

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    wb.save(SALIDA)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--forzar", action="store_true", help="Sobrescribe el banco existente")
    args = p.parse_args()
    if SALIDA.exists() and not args.forzar:
        sys.exit(f"Ya existe {SALIDA.relative_to(RAIZ)}; no se sobrescribe. Use --forzar solo si quiere perder lo escrito.")
    rnd = random.Random(SEMILLA)
    with conectar_ro() as ro, conectar_admin() as admin:
        filas = candidatas(Datos(ro), rnd)
        esquema = describir_esquema(admin, con_descripciones=True)
    escribir_excel(filas, esquema)
    print(f"Plantilla creada: {SALIDA.relative_to(RAIZ)} con {len(filas)} preguntas candidatas")


if __name__ == "__main__":
    main()
