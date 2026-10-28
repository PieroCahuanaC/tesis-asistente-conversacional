"""Clasifica cada pregunta del banco en una «familia» de cálculo con sus parámetros.

La interpretación de cada familia (qué se suma, qué se excluye) queda escrita en INTERPRETACION y se
copia al Excel, para que los investigadores, los expertos y el jurado vean exactamente qué se calculó.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "setiembre", "octubre", "noviembre", "diciembre"], start=1)}
ORDINAL = {"primer": 1, "segundo": 2, "tercer": 3, "cuarto": 4}
NUMEROS = {"tres": 3, "cinco": 5}
_MES = "(" + "|".join(MESES) + ")"

INTERPRETACION = {
    "saldo": "Saldo al cierre del mes = PIM del año de la finalidad − certificación acumulada de enero a ese mes (D13).",
    "pim": "PIM anual de la finalidad (suma de sus metas).",
    "cert_acum": "Certificación acumulada de la finalidad de enero al mes indicado.",
    "cert_mes": "Certificación registrada solo en ese mes (flujo mensual).",
    "dev_rango": "Suma del devengado mensual de la finalidad en los meses indicados (ambos inclusive).",
    "comp_trim": "Suma del compromiso anual registrado en los tres meses del trimestre.",
    "dev_total_mes": "Devengado de todas las finalidades de la municipalidad en ese mes.",
    "dev_total_anio": "Devengado de todas las finalidades en los 12 meses del año.",
    "dev_anual_pct": "Devengado de enero a diciembre de la finalidad y su porcentaje sobre el PIM (2 decimales).",
    "pct_dev": "Devengado anual / PIM × 100 (2 decimales).",
    "ordenes_periodo": "Órdenes ≤ 8 UIT (sin las que derivan de selección) emitidas en el periodo: el conteo incluye anuladas; el monto las excluye (D9).",
    "conteo_periodo": "Número de órdenes ≤ 8 UIT emitidas en el periodo, incluidas las anuladas (D9).",
    "monto_periodo": "Monto de las órdenes ≤ 8 UIT emitidas en el periodo, sin las anuladas (D9).",
    "monto_meta_mes": "Monto de las órdenes ≤ 8 UIT de la finalidad emitidas en ese mes, sin anuladas.",
    "anuladas": "Número de órdenes ≤ 8 UIT con estado «anulada» emitidas en el periodo.",
    "promedio": "Monto promedio de las órdenes ≤ 8 UIT no anuladas del tipo y año (2 decimales).",
    "superan_8uit": "Número de órdenes del año (cualquier tipo de contratación) cuyo monto supera 8 UIT del año.",
    "personas_naturales": "Número de órdenes ≤ 8 UIT del año emitidas a RUC de persona natural (10, 15 o 17), incluidas anuladas.",
    "top_dev": "Finalidades con mayor devengado anual (código y monto), de mayor a menor.",
    "top_dev_periodo": "Finalidades con mayor devengado en los meses indicados.",
    "top_pim": "Finalidades con mayor PIM del año.",
    "top_saldo": "Finalidades con mayor saldo (PIM − certificación acumulada) al cierre del mes.",
    "top_ordenes": "Finalidades con mayor monto de órdenes ≤ 8 UIT no anuladas en el periodo (solo órdenes con código).",
    "bottom_avance": "Finalidades con PIM > 0 de menor avance (devengado anual / PIM × 100).",
    "var_dev": "Diferencia del devengado anual de la finalidad (año 2 − año 1) y variación porcentual sobre el año 1.",
    "var_total": "Diferencia del total municipal (año 2 − año 1) y variación porcentual sobre el año 1.",
    "mes_max_ordenes": "Mes con más órdenes ≤ 8 UIT del tipo (conteo con anuladas) y su número.",
    "mes_max_dev": "Mes con mayor devengado total de la municipalidad y su monto.",
    "trim_max_dev": "Trimestre con mayor devengado total y su monto.",
    "comp_conteo_anios": "Año con más órdenes ≤ 8 UIT (con anuladas) y diferencia de conteo.",
    "comp_tipo_monto": "Tipo de orden con mayor monto (sin anuladas) y diferencia en soles.",
    "comp_metas": "Finalidad con mayor valor y diferencia en soles.",
    "max_orden": "Orden ≤ 8 UIT no anulada de mayor monto del tipo y año: número y monto.",
    "contar_avance_mayor": "Número de finalidades con PIM > 0 cuyo avance (devengado acumulado / PIM × 100) supera el umbral al cierre del mes.",
    "contar_avance_menor": "Número de finalidades con PIM > 0 cuyo avance es menor que el umbral al cierre del mes.",
    "listar_avance_mayor": "Finalidades con PIM > 0 cuyo avance supera el umbral al cierre del mes.",
    "listar_avance_menor": "Finalidades con PIM > 0 cuyo avance es menor que el umbral al cierre del mes.",
    "avance_meta": "Avance de la finalidad al cierre del mes (%) y si supera el umbral.",
    "alcanza": "Saldo al cierre del mes, diferencia (saldo − monto) y resultado (alcanza si la diferencia ≥ 0).",
    "no_respondible": "No respondible con los datos: la respuesta correcta es abstenerse sin cifras.",
}


@dataclass
class Familia:
    nombre: str
    p: dict = field(default_factory=dict)


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _anios(n):
    return [int(a) for a in re.findall(r"\b(20\d\d)\b", n)]


def _meses(n):
    return [MESES[m] for m in re.findall(r"\b" + _MES + r"\b", n)]


def _codigos(n):
    return re.findall(r"\b(\d{7})\b", n)


def _monto(n):
    m = re.search(r"s/ ?([\d ][\d ]*\d)", n)
    return float(m.group(1).replace(" ", "")) if m else None


def _tipo(n):
    if "ordenes de compra" in n or "orden de compra" in n:
        return "O/C"
    if "ordenes de servicio" in n or "orden de servicio" in n:
        return "O/S"
    return None


def _meta(n):
    """Código o nombre de la meta citada."""
    c = _codigos(n)
    if c:
        return {"fin": c[0]}
    m = re.search(r"(?:la meta de |comprometio en (?:la meta de )?)(.+?)(?: al cierre| a fines| en el (?:primer|segundo|tercer|cuarto)"
                  r"| pide| para un| superaba| ya supero)", n)
    if not m:
        raise ValueError("no se identificó la meta")
    return {"nombre": m.group(1).strip()}


def _periodo_trim_sem(n):
    m = re.search(r"(primer|segundo|tercer|cuarto) (trimestre|semestre)", n)
    if not m:
        return None
    k = ORDINAL[m.group(1)]
    return ((k - 1) * 3 + 1, k * 3) if m.group(2) == "trimestre" else ((k - 1) * 6 + 1, k * 6)


def clasificar(pregunta: str, tipo: str, criterio: str) -> Familia:
    n = normalizar(pregunta)
    A, M = _anios(n), _meses(n)
    if criterio == "abstencion" or tipo == "T7":
        return Familia("no_respondible")

    # ---------------- T6 y T5
    if "alcanza" in n and "saldo" in n:
        return Familia("alcanza", {**_meta(n), "monto": _monto(n), "anio": A[0], "mes": M[-1]})
    m = re.search(r"(\d+) ?%", n)
    if tipo == "T5" or "avance" in n or "% de ejecucion" in n:
        u = int(m.group(1))
        if "ya supero" in n or "superaba" in n:
            return Familia("avance_meta", {**_meta(n), "anio": A[0], "mes": M[-1], "umbral": u})
        menor = "menor" in n
        if n.startswith("¿cuantas") or "cuantas metas" in n:
            return Familia("contar_avance_menor" if menor else "contar_avance_mayor", {"anio": A[0], "mes": M[-1], "umbral": u})
        return Familia("listar_avance_menor" if menor else "listar_avance_mayor", {"anio": A[0], "mes": M[-1], "umbral": u})

    # ---------------- T1
    if "faltaba certificar" in n:
        return Familia("saldo", {**_meta(n), "anio": A[0], "mes": M[-1]})
    if "pim de la meta" in n and "saldo" not in n:
        return Familia("pim", {**_meta(n), "anio": A[0]})
    if "se habia certificado en total" in n:
        return Familia("cert_acum", {**_meta(n), "anio": A[0], "mes": M[-1]})
    if "saldo" in n and "metas" not in n or "faltaba certificar" in n:
        return Familia("saldo", {**_meta(n), "anio": A[0], "mes": M[-1]})

    # ---------------- T2
    if "se devengo en la meta" in n:
        return Familia("dev_rango", {**_meta(n), "anio": A[0], "m1": M[0], "m2": M[-1]})
    if "se comprometio en" in n:
        m1, m2 = _periodo_trim_sem(n)
        return Familia("comp_trim", {**_meta(n), "anio": A[0], "m1": m1, "m2": m2})
    if "devengo en total la municipalidad en" in n:
        return Familia("dev_total_mes", {"anio": A[0], "mes": M[0]})
    if "devengado acumulado de la meta" in n:
        return Familia("dev_anual_pct", {**_meta(n), "anio": A[0]})
    if "se certifico en la meta" in n:
        return Familia("cert_mes", {**_meta(n), "anio": A[0], "mes": M[0]})
    if "devengado total de la municipalidad en todo" in n:
        return Familia("dev_total_anio", {"anio": A[0]})
    if "que porcentaje de su pim habia devengado" in n:
        return Familia("pct_dev", {**_meta(n), "anio": A[0]})

    # ---------------- T4 (antes que T3: comparten palabras)
    k = next((v for w, v in NUMEROS.items() if re.search(rf"\b{w}\b", n)), None)
    if "concentraron mas gasto devengado" in n:
        return Familia("top_dev", {"n": k, "anio": A[0]})
    if "mayor pim en" in n and k:
        return Familia("top_pim", {"n": k, "anio": A[0]})
    if "tuvieron mas devengado en el" in n:
        m1, m2 = _periodo_trim_sem(n)
        return Familia("top_dev_periodo", {"n": k, "anio": A[0], "m1": m1, "m2": m2})
    if "mayor saldo sin certificar" in n:
        return Familia("top_saldo", {"n": k, "anio": A[0], "mes": M[-1]})
    if "concentraron el mayor monto en ordenes" in n:
        m1, m2 = (M[0], M[1]) if len(M) == 2 else (1, 12)
        return Familia("top_ordenes", {"n": k, "anio": A[0], "m1": m1, "m2": m2})
    if "menor porcentaje de ejecucion" in n:
        return Familia("bottom_avance", {"n": k, "anio": A[0]})
    if "como vario el devengado anual de la meta" in n:
        return Familia("var_dev", {**_meta(n), "a1": A[0], "a2": A[1]})
    if re.search(r"en cuanto cambio el (pim|devengado) total", n):
        medida = "pim" if "pim total" in n else "devengado"
        return Familia("var_total", {"medida": medida, "a1": A[0], "a2": A[1]})
    if "se emitieron mas ordenes" in n and "en que mes" in n:
        return Familia("mes_max_ordenes", {"tipo": _tipo(n), "anio": A[0]})
    if "en que mes de" in n and "se devengo mas" in n:
        return Familia("mes_max_dev", {"anio": A[0]})
    if "que trimestre de" in n:
        return Familia("trim_max_dev", {"anio": A[0]})
    if "se emitieron mas ordenes" in n and len(A) == 2:
        return Familia("comp_conteo_anios", {"a1": A[0], "a2": A[1]})
    if "las ordenes de compra o las de servicio" in n:
        return Familia("comp_tipo_monto", {"anio": A[0]})
    if re.search(r"que meta tuvo mayor (devengado|pim)", n):
        medida = "pim" if "mayor pim" in n else "devengado"
        c = _codigos(n)
        return Familia("comp_metas", {"medida": medida, "anio": A[0], "f1": c[0], "f2": c[1]})
    if "de mayor monto en" in n:
        return Familia("max_orden", {"tipo": _tipo(n), "anio": A[0]})

    # ---------------- T3
    if "anuladas" in n:
        m1, m2 = (M[0], M[1]) if len(M) == 2 else (1, 12)
        return Familia("anuladas", {"anio": A[0], "m1": m1, "m2": m2})
    if "monto promedio" in n:
        return Familia("promedio", {"tipo": _tipo(n), "anio": A[0]})
    if "superaron el tope de 8 uit" in n:
        return Familia("superan_8uit", {"anio": A[0]})
    if "personas naturales" in n:
        return Familia("personas_naturales", {"anio": A[0]})
    if "monto total de las ordenes" in n and _codigos(n):
        return Familia("monto_meta_mes", {**_meta(n), "anio": A[0], "mes": M[0]})
    per = _periodo_trim_sem(n)
    if per:
        m1, m2 = per
    elif M:
        m1 = m2 = M[0]
    else:
        m1, m2 = 1, 12
    base = {"tipo": _tipo(n), "anio": A[0], "m1": m1, "m2": m2}
    if "cuantas ordenes" in n and "por que monto" in n:
        return Familia("ordenes_periodo", base)
    if "cuantas ordenes" in n:
        return Familia("conteo_periodo", base)
    if "monto total de las ordenes" in n:
        return Familia("monto_periodo", base)
    raise ValueError("pregunta sin familia")
