"""Cálculo A de las respuestas de referencia: una consulta SQL por pregunta sobre la base integrada
(tablas base datos.ejecucion_presupuestal y datos.orden; no usa la vista materializada ni las
herramientas del asistente). Cada SQL se escribe completo en el Excel para que pueda auditarse."""
from __future__ import annotations

from asistente.evaluacion.familias import Familia

E = "datos.ejecucion_presupuestal"
O = "datos.orden"

# Columnas de salida de cada familia (mismas en el cálculo B); definen el Valor_referencia.
COLUMNAS = {
    "saldo": ["saldo"], "pim": ["pim"], "cert_acum": ["certificado"], "cert_mes": ["certificado"],
    "dev_rango": ["devengado"], "comp_trim": ["comprometido"], "dev_total_mes": ["devengado"],
    "dev_total_anio": ["devengado"], "dev_anual_pct": ["devengado", "porcentaje"], "pct_dev": ["porcentaje"],
    "ordenes_periodo": ["conteo", "monto"], "conteo_periodo": ["conteo"], "monto_periodo": ["monto"],
    "monto_meta_mes": ["monto"], "anuladas": ["conteo"], "promedio": ["promedio"], "superan_8uit": ["conteo"],
    "personas_naturales": ["conteo"], "top_dev": ["finalidad", "valor"], "top_dev_periodo": ["finalidad", "valor"],
    "top_pim": ["finalidad", "valor"], "top_saldo": ["finalidad", "valor"], "top_ordenes": ["finalidad", "valor"],
    "bottom_avance": ["finalidad", "porcentaje"], "var_dev": ["diferencia", "porcentaje"],
    "var_total": ["diferencia", "porcentaje"], "mes_max_ordenes": ["mes", "conteo"], "mes_max_dev": ["mes", "monto"],
    "trim_max_dev": ["trimestre", "monto"], "comp_conteo_anios": ["anio", "diferencia"],
    "comp_tipo_monto": ["tipo", "diferencia"], "comp_metas": ["finalidad", "diferencia"],
    "max_orden": ["numero", "monto"], "contar_avance_mayor": ["conteo"], "contar_avance_menor": ["conteo"],
    "listar_avance_mayor": ["finalidad"], "listar_avance_menor": ["finalidad"],
    "avance_meta": ["porcentaje", "supera"], "alcanza": ["saldo", "diferencia", "resultado"],
}
MULTIFILA = {"top_dev", "top_dev_periodo", "top_pim", "top_saldo", "top_ordenes", "bottom_avance",
             "listar_avance_mayor", "listar_avance_menor"}


def _tipo(p):
    return f" AND tipo_orden = '{p['tipo']}'" if p.get("tipo") else ""


def _avance(anio, mes):
    return (f"WITH f AS (SELECT finalidad, sum(pim) AS pim, "
            f"sum(devengado) FILTER (WHERE mes BETWEEN 1 AND {mes}) AS dev "
            f"FROM {E} WHERE anio = {anio} GROUP BY finalidad) ")


def sql(f: Familia) -> str | None:
    p, n = f.p, f.nombre
    fin = p.get("fin")
    if n == "no_respondible":
        return None
    if n == "saldo":
        return (f"SELECT round(sum(pim) - coalesce(sum(certificado) FILTER (WHERE mes BETWEEN 1 AND {p['mes']}), 0), 2) "
                f"FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']}")
    if n == "pim":
        return f"SELECT sum(pim) FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']}"
    if n == "cert_acum":
        return (f"SELECT coalesce(sum(certificado), 0) FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']} "
                f"AND mes BETWEEN 1 AND {p['mes']}")
    if n == "cert_mes":
        return f"SELECT coalesce(sum(certificado), 0) FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']} AND mes = {p['mes']}"
    if n == "dev_rango":
        return (f"SELECT coalesce(sum(devengado), 0) FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']} "
                f"AND mes BETWEEN {p['m1']} AND {p['m2']}")
    if n == "comp_trim":
        return (f"SELECT coalesce(sum(comprometido_anual), 0) FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']} "
                f"AND mes BETWEEN {p['m1']} AND {p['m2']}")
    if n == "dev_total_mes":
        return f"SELECT sum(devengado) FROM {E} WHERE anio = {p['anio']} AND mes = {p['mes']}"
    if n == "dev_total_anio":
        return f"SELECT sum(devengado) FROM {E} WHERE anio = {p['anio']} AND mes BETWEEN 1 AND 12"
    if n in ("dev_anual_pct", "pct_dev"):
        cols = "d, round(100 * d / p, 2)" if n == "dev_anual_pct" else "round(100 * d / p, 2)"
        return (f"SELECT {cols} FROM (SELECT sum(devengado) FILTER (WHERE mes > 0) AS d, sum(pim) AS p "
                f"FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']}) t")
    base_o = f"FROM {O} WHERE incluida AND anio = {p.get('anio')} AND mes BETWEEN {p.get('m1')} AND {p.get('m2')}{_tipo(p)}"
    if n == "ordenes_periodo":
        return f"SELECT count(*), coalesce(sum(monto_soles) FILTER (WHERE estado <> 'anulada'), 0) {base_o}"
    if n == "conteo_periodo":
        return f"SELECT count(*) {base_o}"
    if n == "monto_periodo":
        return f"SELECT coalesce(sum(monto_soles) FILTER (WHERE estado <> 'anulada'), 0) {base_o}"
    if n == "monto_meta_mes":
        return (f"SELECT coalesce(sum(monto_soles), 0) FROM {O} WHERE incluida AND estado <> 'anulada' "
                f"AND codigo_finalidad = '{fin}' AND anio = {p['anio']} AND mes = {p['mes']}")
    if n == "anuladas":
        return (f"SELECT count(*) FROM {O} WHERE incluida AND estado = 'anulada' AND anio = {p['anio']} "
                f"AND mes BETWEEN {p['m1']} AND {p['m2']}")
    if n == "promedio":
        return (f"SELECT round(avg(monto_soles), 2) FROM {O} WHERE incluida AND estado <> 'anulada' "
                f"AND anio = {p['anio']}{_tipo(p)}")
    if n == "superan_8uit":
        return (f"SELECT count(*) FROM {O} o JOIN datos.uit u ON u.anio = o.anio "
                f"WHERE o.anio = {p['anio']} AND o.monto_soles > 8 * u.valor")
    if n == "personas_naturales":
        return f"SELECT count(*) FROM {O} WHERE incluida AND persona_natural AND anio = {p['anio']}"
    if n in ("top_dev", "top_dev_periodo", "top_pim"):
        col = "pim" if n == "top_pim" else "devengado"
        meses = f"AND mes BETWEEN {p['m1']} AND {p['m2']}" if n == "top_dev_periodo" else ("" if n == "top_pim" else "AND mes > 0")
        return (f"SELECT finalidad, sum({col}) AS v FROM {E} WHERE anio = {p['anio']} {meses} "
                f"GROUP BY finalidad ORDER BY v DESC, finalidad LIMIT {p['n']}")
    if n == "top_saldo":
        return (f"SELECT finalidad, sum(pim) - coalesce(sum(certificado) FILTER (WHERE mes BETWEEN 1 AND {p['mes']}), 0) AS v "
                f"FROM {E} WHERE anio = {p['anio']} GROUP BY finalidad ORDER BY v DESC, finalidad LIMIT {p['n']}")
    if n == "top_ordenes":
        return (f"SELECT codigo_finalidad, sum(monto_soles) AS v FROM {O} WHERE incluida AND estado <> 'anulada' "
                f"AND codigo_finalidad IS NOT NULL AND anio = {p['anio']} AND mes BETWEEN {p['m1']} AND {p['m2']} "
                f"GROUP BY codigo_finalidad ORDER BY v DESC, codigo_finalidad LIMIT {p['n']}")
    if n == "bottom_avance":
        return (f"SELECT finalidad, round(100 * coalesce(sum(devengado) FILTER (WHERE mes > 0), 0) / sum(pim), 2) AS av FROM {E} "
                f"WHERE anio = {p['anio']} GROUP BY finalidad HAVING sum(pim) > 0 ORDER BY av, finalidad LIMIT {p['n']}")
    if n == "var_dev":
        return (f"SELECT d2 - d1, round(100 * (d2 - d1) / d1, 2) FROM (SELECT "
                f"sum(devengado) FILTER (WHERE anio = {p['a1']} AND mes > 0) AS d1, "
                f"sum(devengado) FILTER (WHERE anio = {p['a2']} AND mes > 0) AS d2 FROM {E} WHERE finalidad = '{fin}') t")
    if n == "var_total":
        col = "pim" if p["medida"] == "pim" else "devengado"
        return (f"SELECT v2 - v1, round(100 * (v2 - v1) / v1, 2) FROM (SELECT "
                f"sum({col}) FILTER (WHERE anio = {p['a1']}) AS v1, sum({col}) FILTER (WHERE anio = {p['a2']}) AS v2 FROM {E}) t")
    if n == "mes_max_ordenes":
        return (f"SELECT mes, count(*) AS c FROM {O} WHERE incluida AND anio = {p['anio']}{_tipo(p)} "
                f"GROUP BY mes ORDER BY c DESC, mes LIMIT 1")
    if n == "mes_max_dev":
        return (f"SELECT mes, sum(devengado) AS v FROM {E} WHERE anio = {p['anio']} AND mes > 0 "
                f"GROUP BY mes ORDER BY v DESC, mes LIMIT 1")
    if n == "trim_max_dev":
        return (f"SELECT (mes + 2) / 3 AS trimestre, sum(devengado) AS v FROM {E} WHERE anio = {p['anio']} AND mes > 0 "
                f"GROUP BY 1 ORDER BY v DESC LIMIT 1")
    if n == "comp_conteo_anios":
        return (f"SELECT CASE WHEN c1 >= c2 THEN {p['a1']} ELSE {p['a2']} END, abs(c1 - c2) FROM (SELECT "
                f"count(*) FILTER (WHERE anio = {p['a1']}) AS c1, count(*) FILTER (WHERE anio = {p['a2']}) AS c2 "
                f"FROM {O} WHERE incluida) t")
    if n == "comp_tipo_monto":
        return (f"SELECT CASE WHEN oc >= os THEN 'O/C' ELSE 'O/S' END, abs(oc - os) FROM (SELECT "
                f"sum(monto_soles) FILTER (WHERE tipo_orden = 'O/C') AS oc, sum(monto_soles) FILTER (WHERE tipo_orden = 'O/S') AS os "
                f"FROM {O} WHERE incluida AND estado <> 'anulada' AND anio = {p['anio']}) t")
    if n == "comp_metas":
        col = "pim" if p["medida"] == "pim" else "devengado"
        filtro = "" if col == "pim" else " AND mes > 0"
        return (f"SELECT CASE WHEN v1 >= v2 THEN '{p['f1']}' ELSE '{p['f2']}' END, abs(v1 - v2) FROM (SELECT "
                f"sum({col}) FILTER (WHERE finalidad = '{p['f1']}') AS v1, sum({col}) FILTER (WHERE finalidad = '{p['f2']}') AS v2 "
                f"FROM {E} WHERE anio = {p['anio']}{filtro}) t")
    if n == "max_orden":
        return (f"SELECT numero_orden, monto_soles FROM {O} WHERE incluida AND estado <> 'anulada' AND anio = {p['anio']}"
                f"{_tipo(p)} ORDER BY monto_soles DESC, numero_orden LIMIT 1")
    if n in ("contar_avance_mayor", "contar_avance_menor", "listar_avance_mayor", "listar_avance_menor"):
        op = ">" if n.endswith("mayor") else "<"
        sel = "count(*)" if n.startswith("contar") else "finalidad"
        orden = "" if n.startswith("contar") else " ORDER BY finalidad"
        return (_avance(p["anio"], p["mes"]) +
                f"SELECT {sel} FROM f WHERE pim > 0 AND round(100 * coalesce(dev, 0) / pim, 2) {op} {p['umbral']}{orden}")
    if n == "avance_meta":
        return (_avance(p["anio"], p["mes"]) +
                f"SELECT round(100 * coalesce(dev, 0) / pim, 2), CASE WHEN round(100 * coalesce(dev, 0) / pim, 2) > {p['umbral']} "
                f"THEN 'sí' ELSE 'no' END FROM f WHERE finalidad = '{fin}'")
    if n == "alcanza":
        return (f"SELECT s, s - {p['monto']}, CASE WHEN s - {p['monto']} >= 0 THEN 'alcanza' ELSE 'no alcanza' END FROM ("
                f"SELECT round(sum(pim) - coalesce(sum(certificado) FILTER (WHERE mes BETWEEN 1 AND {p['mes']}), 0), 2) AS s "
                f"FROM {E} WHERE finalidad = '{fin}' AND anio = {p['anio']}) t")
    raise ValueError(f"Familia sin SQL: {n}")
