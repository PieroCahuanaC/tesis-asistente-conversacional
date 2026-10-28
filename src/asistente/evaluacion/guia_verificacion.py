"""Pasos para verificar a mano, en Excel, la respuesta de referencia de una pregunta (3.5.3).

La verificación usa los mismos archivos originales que el cálculo B, pero la hace una persona con
filtros y tablas dinámicas de Excel, sin ejecutar código del proyecto.
"""
from __future__ import annotations

from asistente.evaluacion.familias import Familia

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SETIEMBRE", "OCTUBRE",
         "NOVIEMBRE", "DICIEMBRE"]
TOPE = {2023: "39 600", 2024: "41 200", 2025: "42 800"}
CSV_MEF = {2023: "2023-Gasto_UCHUMAYO.csv", 2024: "2024-Gasto_UCHUMAYO.csv", 2025: "2025-Gasto-Mensual_UCHUMAYO.csv"}

PREPARACION = [
    "PREPARACIÓN (una sola vez)",
    "MEF. Por cada año: abrir data/raw/mef/filtrado/<año>…_UCHUMAYO.csv en Excel → Insertar → Tabla dinámica.",
    "   Filtro: FINALIDAD.  Filas: MES_EJE.  Valores: Suma de MONTO_PIM, MONTO_CERTIFICADO, MONTO_COMPROMETIDO_ANUAL y MONTO_DEVENGADO.",
    "   La llamamos «TD-MEF <año>». El PIM solo aparece en la fila MES_EJE = 0; los demás montos van mes a mes (pueden ser negativos: son rebajas).",
    "   Excel quita los ceros a la izquierda del código: la FINALIDAD 0001109 aparece como 1109 (filtrar por ese número).",
    "   Si los montos se ven como texto (alineados a la izquierda), abrir con Datos → Desde texto/CSV y elegir punto como separador decimal.",
    "PTE. Cada archivo data/raw/pte/<año>/PTE_<año>_<mes>_<NOMBRE>.xls tiene las órdenes emitidas en ese mes. Al abrirlo: Datos → Filtro.",
    "   Monto: agregar una columna con =VALOR(SUSTITUIR(J2;\"S/. \";\"\")) y copiarla hacia abajo (si da error, Buscar y reemplazar «S/. » por nada en la columna J).",
    "   Órdenes ≤ 8 UIT = «Tipo de Contratación» distinto de «Deviene de Procesos de Selección» y monto ≤ 8 UIT del año (2023: 39 600; 2024: 41 200; 2025: 42 800).",
    "   Conteo: filas visibles tras filtrar (barra de estado de Excel, «Recuento»). Regla D9: el conteo incluye anuladas; los montos las excluyen (filtrar Estado ≠ Anulada).",
    "",
    "POR CADA PREGUNTA: seguir los pasos, escribir lo que obtuvieron en Valor_encontrado y marcar Resultado = conforme u observada.",
    "Si queda observada, explicar en Comentario (qué valor sale, de qué archivo y filtro). No usar el asistente ni los scripts del proyecto.",
]


def _pte(anio: int, m1: int, m2: int) -> str:
    if m1 == m2:
        return f"data/raw/pte/{anio}/PTE_{anio}_{m1:02d}_{MESES[m1 - 1]}.xls"
    return f"data/raw/pte/{anio}/ (archivos de {MESES[m1 - 1].lower()} a {MESES[m2 - 1].lower()})"


def _mes(m: int) -> str:
    return MESES[m - 1].lower()


def pasos(f: Familia) -> tuple[str, str]:
    """(archivo o fuente, pasos numerados) para verificar la pregunta."""
    p, n = f.p, f.nombre
    anio = p.get("anio") or p.get("a1")
    mef = f"data/raw/mef/filtrado/{CSV_MEF.get(anio, '')}"
    fin = p.get("fin")
    meta = f"FINALIDAD = {fin}" if fin else ""
    if "nombre" in p:
        meta = (f"la finalidad cuyo META_NOMBRE contiene «{p['nombre']}» (en el CSV, filtrar META_NOMBRE con «Contiene»; "
                f"anotar su código FINALIDAD: debe ser {fin})")

    if n == "no_respondible":
        return ("Archivos del PTE y del MEF, y la pregunta misma",
                "1. Identificar qué dato pide la pregunta (periodo, entidad, campo).\n"
                "2. Confirmar que NO está en los datos: año fuera de 2023-2025, otra municipalidad, un campo que no existe "
                "(proveedor de persona natural, motivo de anulación, funcionario, sueldos) o un mes del tramo 2024-08 a 2025-03 "
                "sin código de finalidad ni estado actualizado (abrir ese archivo del PTE y revisar las columnas «Descripción» y «Estado»).\n"
                "3. Conforme = la información realmente no existe en las fuentes.")
    if n in ("saldo", "alcanza"):
        t = (f"1. En TD-MEF {anio}, filtrar {meta}.\n"
             f"2. PIM = Suma de MONTO_PIM (fila 0 / total general).\n"
             f"3. Certificación acumulada = suma de MONTO_CERTIFICADO de los meses 1 a {p['mes']} ({_mes(1)} a {_mes(p['mes'])}).\n"
             f"4. Saldo = PIM − certificación acumulada.")
        if n == "alcanza":
            t += f"\n5. Diferencia = saldo − {p['monto']:,.0f}. Alcanza si la diferencia es ≥ 0."
        return mef, t
    if n == "pim":
        return mef, f"1. En TD-MEF {anio}, filtrar {meta}.\n2. PIM = Suma de MONTO_PIM."
    if n in ("cert_mes", "cert_acum"):
        rango = f"solo el mes {p['mes']}" if n == "cert_mes" else f"los meses 1 a {p['mes']}"
        return mef, f"1. En TD-MEF {anio}, filtrar {meta}.\n2. Sumar MONTO_CERTIFICADO de {rango} (si el mes no aparece, es 0)."
    if n in ("dev_rango", "comp_trim"):
        col = "MONTO_DEVENGADO" if n == "dev_rango" else "MONTO_COMPROMETIDO_ANUAL"
        return mef, (f"1. En TD-MEF {anio}, filtrar {meta}.\n2. Sumar {col} de los meses {p['m1']} a {p['m2']} "
                     f"({_mes(p['m1'])} a {_mes(p['m2'])}); un mes que no aparece vale 0.")
    if n == "dev_total_mes":
        return mef, f"1. En TD-MEF {anio}, FINALIDAD = (Todas).\n2. Leer Suma de MONTO_DEVENGADO de la fila MES_EJE = {p['mes']}."
    if n == "dev_total_anio":
        return mef, f"1. En TD-MEF {anio}, FINALIDAD = (Todas).\n2. Leer Suma de MONTO_DEVENGADO del total general."
    if n in ("dev_anual_pct", "pct_dev"):
        return mef, (f"1. En TD-MEF {anio}, filtrar {meta}.\n2. Devengado anual = total de MONTO_DEVENGADO; PIM = total de MONTO_PIM.\n"
                     "3. Porcentaje = devengado / PIM × 100, con 2 decimales.")
    if n == "var_dev":
        return (f"data/raw/mef/filtrado/{CSV_MEF[p['a1']]} y {CSV_MEF[p['a2']]}",
                f"1. En TD-MEF {p['a1']} y TD-MEF {p['a2']}, filtrar FINALIDAD = {fin} y leer el total de MONTO_DEVENGADO de cada año.\n"
                f"2. Diferencia = devengado {p['a2']} − devengado {p['a1']}; variación % = diferencia / devengado {p['a1']} × 100.")
    if n == "var_total":
        col = "MONTO_PIM" if p["medida"] == "pim" else "MONTO_DEVENGADO"
        return (f"data/raw/mef/filtrado/{CSV_MEF[p['a1']]} y {CSV_MEF[p['a2']]}",
                f"1. En TD-MEF {p['a1']} y TD-MEF {p['a2']}, FINALIDAD = (Todas): leer el total general de {col}.\n"
                f"2. Diferencia = {p['a2']} − {p['a1']}; variación % = diferencia / valor {p['a1']} × 100.")
    if n == "trim_max_dev":
        return mef, (f"1. En TD-MEF {anio}, FINALIDAD = (Todas).\n2. Sumar MONTO_DEVENGADO por trimestre: meses 1-3, 4-6, 7-9 y 10-12.\n"
                     "3. Anotar el trimestre mayor y su monto.")
    if n == "mes_max_dev":
        return mef, f"1. En TD-MEF {anio}, FINALIDAD = (Todas).\n2. Ver qué mes (1-12) tiene la mayor suma de MONTO_DEVENGADO."
    if n in ("contar_avance_mayor", "contar_avance_menor", "listar_avance_mayor", "listar_avance_menor", "bottom_avance",
             "avance_meta"):
        mes = p.get("mes", 12)
        t = (f"1. En el CSV de {anio}, agregar una columna DEV_HASTA = SI(Y(MES_EJE>=1;MES_EJE<={mes});MONTO_DEVENGADO;0).\n"
             "2. Nueva tabla dinámica: Filas FINALIDAD; Valores Suma de MONTO_PIM y Suma de DEV_HASTA.\n"
             "3. Avance % = devengado acumulado / PIM × 100 (2 decimales). Ignorar finalidades con PIM = 0.\n")
        if n == "avance_meta":
            t += f"4. Buscar {meta} y comparar su avance con {p['umbral']} %."
        elif n == "bottom_avance":
            t += f"4. Ordenar el avance de menor a mayor y anotar las {p['n']} primeras (una sin devengado tiene 0 %)."
        else:
            op = "mayor que" if n.endswith("mayor") else "menor que"
            t += f"4. {'Contar' if n.startswith('contar') else 'Listar'} las finalidades con avance {op} {p['umbral']} %."
        return mef, t
    if n in ("top_dev", "top_dev_periodo", "top_pim", "top_saldo"):
        return mef, ("1. En el CSV, tabla dinámica con Filas FINALIDAD y Columnas MES_EJE.\n"
                     "2. Calcular el valor que pide la pregunta por finalidad y ordenar de mayor a menor.\n"
                     f"3. Anotar las {p['n']} primeras.")
    if n == "comp_metas":
        col = "MONTO_PIM" if p["medida"] == "pim" else "MONTO_DEVENGADO"
        return mef, (f"1. En TD-MEF {anio}, leer el total de {col} con FINALIDAD = {p['f1']} y luego con FINALIDAD = {p['f2']}.\n"
                     "2. Anotar cuál es mayor y la diferencia.")

    # ---- órdenes del PTE
    tipo = {"O/C": "«Tipo de Orden» = O/C (compra); ", "O/S": "«Tipo de Orden» = O/S (servicio); "}.get(p.get("tipo"), "")
    base = (f"Filtrar {tipo}«Tipo de Contratación» ≠ «Deviene de Procesos de Selección»; "
            f"monto ≤ {TOPE.get(anio, '')}.")
    if n in ("conteo_periodo", "ordenes_periodo", "monto_periodo", "anuladas"):
        m1, m2 = p.get("m1", 1), p.get("m2", 12)
        t = f"1. Abrir cada archivo del periodo. {base}\n"
        if n == "anuladas":
            t += "2. Filtrar además Estado = Anulada y contar las filas.\n"
        else:
            t += "2. Conteo = filas visibles (incluye anuladas).\n"
            if n != "conteo_periodo":
                t += "3. Monto = suma de la columna de monto con Estado ≠ Anulada.\n"
        if m1 != m2:
            t += "Anotar el resultado de cada mes en una tablita y sumar todos los meses."
        return _pte(anio, m1, m2), t
    if n == "monto_meta_mes":
        return _pte(anio, p["mes"], p["mes"]), (f"1. {base}\n2. Filtrar Estado ≠ Anulada y que la Descripción "
                                                  f"contenga «{fin}» (el código va después de un guion).\n3. Sumar el monto.")
    if n == "promedio":
        return _pte(anio, 1, 12), (f"1. En cada mes: {base} Estado ≠ Anulada. Anotar la suma de montos y el número de filas.\n"
                                   "2. Promedio = suma de los 12 montos / suma de los 12 conteos (2 decimales).")
    if n == "personas_naturales":
        return _pte(anio, 1, 12), (f"1. En cada mes: {base}\n2. Filtrar RUC que empieza con 10, 15 o 17 (Filtro de texto → Comienza por; "
                                   "o una columna =IZQUIERDA(K2;2)). Contar filas, con anuladas.\n3. Sumar los 12 meses.")
    if n == "mes_max_ordenes":
        return _pte(anio, 1, 12), f"1. En cada mes: {base} Contar filas (con anuladas).\n2. Anotar el mes con más órdenes y su conteo."
    if n == "comp_conteo_anios":
        return (f"data/raw/pte/{p['a1']}/ y data/raw/pte/{p['a2']}/",
                "1. En cada mes de los dos años: Tipo de Contratación ≠ Deviene de Procesos de Selección, monto ≤ 8 UIT del año. "
                "Contar filas (con anuladas).\n2. Sumar por año; anotar el año mayor y la diferencia.")
    if n == "comp_tipo_monto":
        return _pte(anio, 1, 12), ("1. En cada mes: ≤ 8 UIT, sin «Deviene…», Estado ≠ Anulada. Sumar montos por separado para O/C y O/S.\n"
                                   "2. Anotar cuál es mayor en el año y la diferencia.")
    if n in ("max_orden", "max_monto_conteo"):
        t = f"1. En cada mes: {base} Estado ≠ Anulada. Ordenar el monto de mayor a menor.\n2. Comparar los 12 meses: monto más alto"
        t += " y número de orden." if n == "max_orden" else " y cuántas órdenes tienen exactamente ese monto."
        return _pte(anio, 1, 12), t
    if n == "superan_8uit":
        return _pte(anio, 1, 12), f"1. En cada mes, contar filas con monto > {TOPE[anio]} (cualquier tipo de contratación).\n2. Sumar los 12 meses."
    if n == "top_ordenes":
        return _pte(anio, p["m1"], p["m2"]), ("1. Unir los meses del periodo (copiar y pegar en una hoja), ≤ 8 UIT, sin «Deviene…», Estado ≠ Anulada.\n"
                                              "2. Extraer el código de 7 dígitos de la Descripción, tabla dinámica por código sumando el monto.\n"
                                              f"3. Ordenar y anotar los {p['n']} primeros.")
    return "", "Verificar con la fuente correspondiente."
