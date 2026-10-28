"""Herramientas de C3 sobre la ejecución presupuestal (Tabla 11, RF-06 a RF-10).

Todas trabajan por FINALIDAD (código de 7 dígitos), que es lo que el funcionario llama «meta» y
lo que figura en las órdenes; una finalidad puede abarcar varias metas (SEC_FUNC) del año.
Saldo al cierre de un mes = PIM vigente a la fecha de corte - certificación acumulada a ese mes
(decisión D13). Ninguna herramienta proyecta montos futuros.
"""
from __future__ import annotations

import psycopg

from asistente.herramientas.comun import (FUENTE_MEF, FUENTE_PTE, NoDisponible, fecha_corte, leer,
                                          meses_en_tramo, no_disponible, soles, validar_finalidad,
                                          validar_periodo, validar_rango)


def _envolver(funcion):
    """Convierte NoDisponible en una respuesta disponible=False (abstención de la herramienta)."""
    def envuelta(conn, **kw):
        try:
            return funcion(conn, **kw)
        except NoDisponible as e:
            return no_disponible(str(e), parametros=kw)
    envuelta.__name__ = funcion.__name__
    envuelta.__doc__ = funcion.__doc__
    return envuelta


def _normalizar(texto: str) -> str:
    tabla = str.maketrans("ÁÉÍÓÚÜÑáéíóúüñ", "AEIOUUNAEIOUUN")
    return texto.translate(tabla).upper()


_SQL_NORMALIZAR = "translate(upper({}), 'ÁÉÍÓÚÜÑ', 'AEIOUUN')"


# ---------------------------------------------------------------- buscar_meta
@_envolver
def buscar_meta(conn: psycopg.Connection, texto: str, anio: int | None = None) -> dict:
    texto = (texto or "").strip()
    if len(texto) < 3:
        raise NoDisponible("Escriba al menos 3 caracteres del nombre de la meta")
    if anio is not None and anio not in (2023, 2024, 2025):
        raise NoDisponible("Solo hay datos de 2023, 2024 y 2025")
    palabras = [p for p in _normalizar(texto).split() if len(p) >= 3] or [_normalizar(texto)]
    condiciones = " AND ".join(f"{_SQL_NORMALIZAR.format('nombre_meta')} LIKE %s" for _ in palabras)
    parametros = [f"%{p}%" for p in palabras]
    filtro_anio = ""
    if anio is not None:
        filtro_anio = " AND anio = %s"
        parametros.append(anio)
    if texto.isdigit() and len(texto) == 7:
        condiciones, parametros = "finalidad = %s", [texto] + parametros[len(palabras):]
    filas = leer(conn, f"""
        SELECT finalidad, max(nombre_meta) AS nombre, array_agg(DISTINCT anio ORDER BY anio) AS anios,
               sum(pim) FILTER (WHERE mes = 1) AS pim_total
        FROM datos.v_finalidad_mes
        WHERE {condiciones}{filtro_anio}
        GROUP BY finalidad ORDER BY pim_total DESC NULLS LAST LIMIT 10""", parametros)
    if not filas:
        raise NoDisponible(f"No se encontró ninguna meta cuyo nombre contenga «{texto}»")
    return {
        "disponible": True,
        "coincidencias": [{"codigo_finalidad": f, "nombre": n, "anios": list(a)} for f, n, a, _ in filas],
        "fuente": FUENTE_MEF,
        "fecha_corte": fecha_corte(conn, "MEF"),
    }


# ---------------------------------------------------------------- consultar_saldo
def _situacion(conn, codigo: str, periodo: str) -> dict:
    anio, mes = map(int, periodo.split("-"))
    filas = leer(conn, """
        SELECT nombre_meta, pia, pim, certificado_acum, comprometido_acum, devengado_acum, saldo,
               avance_devengado_pct
        FROM datos.v_finalidad_mes WHERE finalidad = %s AND anio = %s AND mes = %s""", (codigo, anio, mes))
    if not filas:
        raise NoDisponible(f"La finalidad {codigo} no tiene presupuesto registrado en {anio}")
    nombre, pia, pim, cert, comp, dev, saldo, avance = filas[0]
    return {"codigo_finalidad": codigo, "nombre": nombre, "periodo": periodo, "pia": soles(pia),
            "pim": soles(pim), "certificado_acumulado": soles(cert), "comprometido_acumulado": soles(comp),
            "devengado_acumulado": soles(dev), "saldo": soles(saldo),
            "avance_devengado_pct": float(avance) if avance is not None else None}


@_envolver
def consultar_saldo(conn: psycopg.Connection, codigo_finalidad: str, periodo: str) -> dict:
    validar_finalidad(codigo_finalidad)
    validar_periodo(periodo)
    return {"disponible": True, **_situacion(conn, codigo_finalidad, periodo),
            "definicion_saldo": "PIM vigente a la fecha de corte menos la certificación acumulada de enero al mes consultado",
            "fuente": FUENTE_MEF, "fecha_corte": fecha_corte(conn, "MEF")}


# ---------------------------------------------------------------- evaluar_requerimiento
@_envolver
def evaluar_requerimiento(conn: psycopg.Connection, codigo_finalidad: str, monto: float, periodo: str) -> dict:
    validar_finalidad(codigo_finalidad)
    validar_periodo(periodo)
    try:
        monto = float(monto)
    except (TypeError, ValueError):
        raise NoDisponible("El monto debe ser un número en soles") from None
    if monto <= 0:
        raise NoDisponible("El monto del requerimiento debe ser mayor que cero")
    s = _situacion(conn, codigo_finalidad, periodo)
    diferencia = round(s["saldo"] - monto, 2)
    return {"disponible": True, "codigo_finalidad": codigo_finalidad, "nombre": s["nombre"],
            "periodo": periodo, "monto_requerimiento": round(monto, 2), "saldo_disponible": s["saldo"],
            "diferencia": diferencia, "resultado": "alcanza" if diferencia >= 0 else "no alcanza",
            "nota": "Resultado orientador: no reemplaza la certificación presupuestal ni proyecta el saldo futuro",
            "fuente": FUENTE_MEF, "fecha_corte": fecha_corte(conn, "MEF")}


# ---------------------------------------------------------------- consultar_ejecucion
@_envolver
def consultar_ejecucion(conn: psycopg.Connection, desde: str, hasta: str,
                        codigo_finalidad: str | None = None) -> dict:
    validar_rango(desde, hasta)
    if codigo_finalidad is not None:
        validar_finalidad(codigo_finalidad)
    filtro = "AND finalidad = %(f)s" if codigo_finalidad else ""
    p = {"desde": desde, "hasta": hasta, "f": codigo_finalidad}
    fila = leer(conn, f"""
        SELECT count(*), coalesce(sum(certificado), 0), coalesce(sum(comprometido_anual), 0),
               coalesce(sum(devengado), 0), coalesce(sum(girado), 0)
        FROM datos.ejecucion_presupuestal
        WHERE mes > 0 AND to_char(make_date(anio, mes, 1), 'YYYY-MM') BETWEEN %(desde)s AND %(hasta)s {filtro}""", p)[0]
    if codigo_finalidad and fila[0] == 0:
        existe = leer(conn, "SELECT 1 FROM datos.ejecucion_presupuestal WHERE finalidad = %s LIMIT 1", (codigo_finalidad,))
        if not existe:
            raise NoDisponible(f"La finalidad {codigo_finalidad} no figura en la ejecución presupuestal")
    resultado = {"disponible": True, "desde": desde, "hasta": hasta, "codigo_finalidad": codigo_finalidad,
                 "certificado": soles(fila[1]), "comprometido": soles(fila[2]),
                 "devengado": soles(fila[3]), "girado": soles(fila[4]),
                 "fuente": FUENTE_MEF, "fecha_corte": fecha_corte(conn, "MEF")}
    # PIM (monto anual, D13) de cada año del rango, de la meta o de toda la municipalidad.
    pims = leer(conn, f"""
        SELECT anio, coalesce(sum(pim), 0) FROM datos.ejecucion_presupuestal
        WHERE anio BETWEEN %(a1)s AND %(a2)s {filtro} GROUP BY anio ORDER BY anio""",
                p | {"a1": int(desde[:4]), "a2": int(hasta[:4])})
    resultado["pim_anual"] = {str(a): soles(v) for a, v in pims}
    if codigo_finalidad:
        nombre = leer(conn, "SELECT max(nombre_meta) FROM datos.ejecucion_presupuestal WHERE finalidad = %s",
                      (codigo_finalidad,))[0][0]
        resultado["nombre"] = nombre

    # Monto de las órdenes <= 8 UIT del mismo periodo (sin anuladas), si el portal publica el código.
    tramo = meses_en_tramo(desde, hasta)
    if codigo_finalidad and tramo:
        resultado["monto_ordenes_8uit"] = None
        resultado["advertencia_ordenes"] = (f"El portal no publica el código de finalidad de las órdenes entre "
                                            f"{tramo[0]} y {tramo[-1]}; no se puede sumar sus órdenes en ese periodo")
    else:
        filtro_o = "AND codigo_finalidad = %(f)s" if codigo_finalidad else ""
        monto = leer(conn, f"""
            SELECT coalesce(sum(monto_soles), 0) FROM datos.orden
            WHERE incluida AND estado <> 'anulada'
              AND to_char(fecha_emision, 'YYYY-MM') BETWEEN %(desde)s AND %(hasta)s {filtro_o}""", p)[0][0]
        resultado["monto_ordenes_8uit"] = soles(monto)
        resultado["fuente_ordenes"] = FUENTE_PTE
    return resultado


# ---------------------------------------------------------------- ranking_metas
CRITERIOS = {
    "devengado": "Monto devengado en el año (gasto ejecutado)",
    "certificado": "Monto certificado en el año",
    "pim": "Presupuesto institucional modificado",
    "avance": "Porcentaje de avance del devengado respecto del PIM",
    "monto_ordenes": "Monto de las órdenes <= 8 UIT emitidas (sin anuladas)",
    "saldo": "Saldo sin certificar (PIM menos certificación acumulada) al cierre del mes",
}


@_envolver
def ranking_metas(conn: psycopg.Connection, anio: int, criterio: str = "devengado", n: int = 5,
                  mes: int = 12) -> dict:
    if anio not in (2023, 2024, 2025):
        raise NoDisponible("Solo hay datos de 2023, 2024 y 2025")
    if criterio not in CRITERIOS:
        raise NoDisponible(f"Criterio no válido; use uno de {sorted(CRITERIOS)}")
    if not isinstance(n, int) or not 1 <= n <= 20:
        raise NoDisponible("n debe estar entre 1 y 20")
    if not isinstance(mes, int) or not 1 <= mes <= 12:
        raise NoDisponible("mes debe estar entre 1 y 12")
    if criterio == "monto_ordenes":
        tramo = meses_en_tramo(f"{anio}-01", f"{anio}-12")
        if tramo:
            raise NoDisponible(f"El portal no publica el código de finalidad de las órdenes entre {tramo[0]} y "
                               f"{tramo[-1]}; no se puede ordenar las metas por monto de órdenes en {anio}")
        filas = leer(conn, """
            SELECT o.codigo_finalidad, coalesce(f.nombre_mef, f.nombre_pte), sum(o.monto_soles) AS valor
            FROM datos.orden o JOIN datos.finalidad f USING (codigo_finalidad)
            WHERE o.incluida AND o.estado <> 'anulada' AND o.anio = %s
            GROUP BY 1, 2 ORDER BY valor DESC, 1 LIMIT %s""", (anio, n))
    else:
        columna = {"devengado": "devengado_acum", "certificado": "certificado_acum", "pim": "pim",
                   "avance": "avance_devengado_pct", "saldo": "saldo"}[criterio]
        extra = "AND pim > 0" if criterio == "avance" else ""
        filas = leer(conn, f"""
            SELECT finalidad, nombre_meta, {columna} AS valor FROM datos.v_finalidad_mes
            WHERE anio = %s AND mes = %s {extra} AND {columna} IS NOT NULL
            ORDER BY valor DESC, finalidad LIMIT %s""", (anio, mes, n))
    return {"disponible": True, "anio": anio, "criterio": criterio, "descripcion_criterio": CRITERIOS[criterio],
            "al_cierre_de": None if criterio in ("pim", "monto_ordenes") else f"{anio}-{mes:02d}",
            "ranking": [{"posicion": i, "codigo_finalidad": f, "nombre": nom,
                         "valor": float(v) if criterio == "avance" else soles(v)}
                        for i, (f, nom, v) in enumerate(filas, start=1)],
            "fuente": FUENTE_PTE if criterio == "monto_ordenes" else FUENTE_MEF,
            "fecha_corte": fecha_corte(conn, "PTE" if criterio == "monto_ordenes" else "MEF")}


# ---------------------------------------------------------------- alertas_ejecucion
@_envolver
def alertas_ejecucion(conn: psycopg.Connection, periodo: str, umbral_pct: float = 80, condicion: str = "mayor") -> dict:
    validar_periodo(periodo)
    try:
        umbral_pct = float(umbral_pct)
    except (TypeError, ValueError):
        raise NoDisponible("El umbral debe ser un porcentaje numérico") from None
    if not 0 < umbral_pct <= 100:
        raise NoDisponible("El umbral debe estar entre 0 y 100 %")
    if condicion not in ("mayor", "menor"):
        raise NoDisponible("condicion debe ser 'mayor' o 'menor'")
    anio, mes = map(int, periodo.split("-"))
    op, orden = (">", "DESC") if condicion == "mayor" else ("<", "ASC")
    filas = leer(conn, f"""
        SELECT finalidad, nombre_meta, pim, devengado_acum, avance_devengado_pct
        FROM datos.v_finalidad_mes
        WHERE anio = %s AND mes = %s AND pim > 0 AND avance_devengado_pct {op} %s
        ORDER BY avance_devengado_pct {orden}, finalidad""", (anio, mes, umbral_pct))
    return {"disponible": True, "periodo": periodo, "umbral_pct": umbral_pct, "condicion": f"avance {condicion} que el umbral",
            "indicador": "devengado acumulado / PIM", "cantidad": len(filas),
            "metas": [{"codigo_finalidad": f, "nombre": n, "pim": soles(p), "devengado_acumulado": soles(d),
                       "avance_pct": float(a)} for f, n, p, d, a in filas],
            "fuente": FUENTE_MEF, "fecha_corte": fecha_corte(conn, "MEF")}


# ---------------------------------------------------------------- esquemas para el modelo
def _esquema(nombre: str, descripcion: str, propiedades: dict, requeridos: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": nombre, "description": descripcion,
        "parameters": {"type": "object", "properties": propiedades, "required": requeridos,
                       "additionalProperties": False}}}


_FIN = {"type": "string", "pattern": "^\\d{7}$", "description": "Código de finalidad (meta) de 7 dígitos, p. ej. 0006508"}
_PER = {"type": "string", "description": "Mes en formato AAAA-MM (enero de 2023 a diciembre de 2025)"}

ESQUEMAS = {
    "buscar_meta": _esquema(
        "buscar_meta",
        "Busca metas (finalidades) presupuestales de la Municipalidad Distrital de Uchumayo por su nombre o "
        "parte de él y devuelve sus códigos de 7 dígitos. Úsela cuando el usuario nombra la meta sin su código.",
        {"texto": {"type": "string", "description": "Nombre o parte del nombre, p. ej. 'parques y jardines'"},
         "anio": {"type": "integer", "enum": [2023, 2024, 2025]}},
        ["texto"]),
    "consultar_saldo": _esquema(
        "consultar_saldo",
        "Devuelve, para una meta y un mes, el PIM, la certificación, el compromiso y el devengado acumulados "
        "al cierre de ese mes y el saldo disponible (PIM menos certificación acumulada).",
        {"codigo_finalidad": _FIN, "periodo": _PER}, ["codigo_finalidad", "periodo"]),
    "consultar_ejecucion": _esquema(
        "consultar_ejecucion",
        "Suma la certificación, el compromiso, el devengado y el girado registrados en un rango de meses, "
        "para una meta o para toda la municipalidad (sin código), el PIM anual de cada año del rango y el monto "
        "de las órdenes <= 8 UIT del mismo rango.",
        {"desde": _PER, "hasta": _PER, "codigo_finalidad": _FIN}, ["desde", "hasta"]),
    "ranking_metas": _esquema(
        "ranking_metas",
        "Ordena las metas de un año de mayor a menor según un criterio y devuelve las n primeras. Los montos "
        "acumulados, el avance y el saldo se calculan al cierre del mes indicado (por defecto, diciembre).",
        {"anio": {"type": "integer", "enum": [2023, 2024, 2025]},
         "criterio": {"type": "string", "enum": sorted(CRITERIOS), "description": "; ".join(f"{k}: {v}" for k, v in CRITERIOS.items())},
         "n": {"type": "integer", "minimum": 1, "maximum": 20},
         "mes": {"type": "integer", "minimum": 1, "maximum": 12, "description": "Mes de cierre (1-12); por defecto 12"}},
        ["anio", "criterio"]),
    "alertas_ejecucion": _esquema(
        "alertas_ejecucion",
        "Lista y cuenta las metas cuyo avance (devengado acumulado / PIM) al cierre de un mes es mayor o menor que "
        "un porcentaje.",
        {"periodo": _PER, "umbral_pct": {"type": "number", "description": "Porcentaje, p. ej. 80"},
         "condicion": {"type": "string", "enum": ["mayor", "menor"],
                       "description": "mayor: avance por encima del umbral (por defecto); menor: por debajo"}},
        ["periodo"]),
    "evaluar_requerimiento": _esquema(
        "evaluar_requerimiento",
        "Indica si el saldo disponible de una meta al cierre de un mes alcanza para un requerimiento de un monto "
        "dado. Devuelve el saldo, la diferencia y el resultado. No proyecta saldos futuros.",
        {"codigo_finalidad": _FIN, "monto": {"type": "number", "description": "Monto del requerimiento en soles"},
         "periodo": _PER},
        ["codigo_finalidad", "monto", "periodo"]),
}

FUNCIONES = {
    "buscar_meta": buscar_meta,
    "consultar_saldo": consultar_saldo,
    "consultar_ejecucion": consultar_ejecucion,
    "ranking_metas": ranking_metas,
    "alertas_ejecucion": alertas_ejecucion,
    "evaluar_requerimiento": evaluar_requerimiento,
}
