"""Herramienta de C3: agregar_ordenes (Tabla 11, RF-08).

Cuenta y suma las órdenes <= 8 UIT de un periodo, con filtros opcionales. Usa SQL parametrizado
con el rol de solo lectura: el modelo elige la herramienta y sus parámetros, nunca escribe SQL.

Reglas de cálculo (deben coincidir con el diccionario semántico de C2 y con las referencias):
- Solo órdenes incluidas (<= 8 UIT y que no derivan de procedimiento de selección).
- conteo_ordenes incluye las anuladas; monto_total_soles las excluye (sección 3.4).
- Filtros por código de finalidad o por estado: no se responden si el periodo toca el tramo
  ago-2024 a mar-2025, en el que el portal no publica esos campos (R-05).
"""
from __future__ import annotations

import re
from decimal import Decimal

import psycopg

from asistente.config import ajustes
from asistente.ingesta.limpieza import ESTADOS

_RE_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

ESQUEMA = {
    "type": "function",
    "function": {
        "name": "agregar_ordenes",
        "description": (
            "Cuenta las órdenes de compra (O/C) y de servicio (O/S) menores o iguales a 8 UIT de la "
            "Municipalidad Distrital de Uchumayo emitidas en un periodo y suma su monto en soles. "
            "Puede filtrar por tipo de orden, código de finalidad (meta) y estado. "
            "El conteo incluye las órdenes anuladas; el monto las excluye. "
            "Datos disponibles: enero de 2023 a diciembre de 2025."),
        "parameters": {
            "type": "object",
            "properties": {
                "desde": {"type": "string", "description": "Mes inicial, formato AAAA-MM"},
                "hasta": {"type": "string", "description": "Mes final inclusive, formato AAAA-MM"},
                "tipo_orden": {"type": "string", "enum": ["O/C", "O/S"],
                               "description": "O/C = orden de compra; O/S = orden de servicio. Omitir para ambas."},
                "codigo_finalidad": {"type": "string", "pattern": "^\\d{7}$",
                                     "description": "Código de finalidad de 7 dígitos, p. ej. 0000888"},
                "estado": {"type": "string", "enum": sorted(ESTADOS)},
            },
            "required": ["desde", "hasta"],
            "additionalProperties": False,
        },
    },
}


def _meses(desde: str, hasta: str) -> list[str]:
    a, m = map(int, desde.split("-"))
    b, n = map(int, hasta.split("-"))
    salida = []
    while (a, m) <= (b, n):
        salida.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida


def agregar_ordenes(conn: psycopg.Connection, desde: str, hasta: str, tipo_orden: str | None = None,
                    codigo_finalidad: str | None = None, estado: str | None = None) -> dict:
    cfg = ajustes()
    filtros = {"desde": desde, "hasta": hasta, "tipo_orden": tipo_orden,
               "codigo_finalidad": codigo_finalidad, "estado": estado}

    def no_disponible(motivo: str, **extra) -> dict:
        return {"disponible": False, "motivo": motivo, "filtros": filtros, **extra}

    if not (_RE_PERIODO.match(desde or "") and _RE_PERIODO.match(hasta or "")):
        return no_disponible("Periodo inválido: use el formato AAAA-MM")
    if desde > hasta:
        return no_disponible("El mes inicial es posterior al mes final")
    if desde < cfg["periodo"]["desde"] or hasta > cfg["periodo"]["hasta"]:
        return no_disponible(f"Solo hay datos de {cfg['periodo']['desde']} a {cfg['periodo']['hasta']}")
    if tipo_orden not in (None, "O/C", "O/S"):
        return no_disponible("tipo_orden debe ser O/C u O/S")
    if estado is not None and estado not in ESTADOS:
        return no_disponible(f"estado debe ser uno de {sorted(ESTADOS)}")
    if codigo_finalidad is not None and not re.fullmatch(r"\d{7}", codigo_finalidad):
        return no_disponible("codigo_finalidad debe tener 7 dígitos")

    tramo = cfg["tramo_sin_codigo_ni_estado"]
    meses = _meses(desde, hasta)
    afectados = [m for m in meses if tramo["desde"] <= m <= tramo["hasta"]]
    if afectados and (codigo_finalidad or estado):
        campo = "el código de finalidad" if codigo_finalidad else "el estado de las órdenes"
        return no_disponible(
            f"El portal no publica {campo} entre {tramo['desde']} y {tramo['hasta']}; "
            "no es posible responder con exactitud para ese periodo.", meses_sin_dato=afectados)

    condiciones = ["incluida", "to_char(fecha_emision, 'YYYY-MM') BETWEEN %(desde)s AND %(hasta)s"]
    if tipo_orden:
        condiciones.append("tipo_orden = %(tipo_orden)s")
    if codigo_finalidad:
        condiciones.append("codigo_finalidad = %(codigo_finalidad)s")
    if estado:
        condiciones.append("estado = %(estado)s")
    consulta = f"""
        SELECT count(*)                                              AS conteo_ordenes,
               count(*) FILTER (WHERE estado = 'anulada')            AS conteo_anuladas,
               coalesce(sum(monto_soles) FILTER (WHERE estado <> 'anulada'), 0) AS monto_total_soles
        FROM datos.orden WHERE {' AND '.join(condiciones)}"""
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        conteo, anuladas, monto = conn.execute(consulta, filtros).fetchone()
        corte = conn.execute("SELECT max(fecha_corte) FROM datos.carga WHERE fuente = 'PTE'").fetchone()[0]

    resultado = {
        "disponible": True,
        "filtros": filtros,
        "conteo_ordenes": conteo,
        "conteo_anuladas": anuladas,
        "monto_total_soles": float(Decimal(monto).quantize(Decimal("0.01"))),
        "fuente": "Portal de Transparencia Estándar, órdenes de compra y de servicio",
        "fecha_corte": corte.isoformat() if corte else None,
    }
    if afectados:
        resultado["advertencia"] = (
            f"Entre {afectados[0]} y {afectados[-1]} el portal no publica el estado real de las órdenes: "
            "las anuladas de esos meses no pueden identificarse y su monto podría estar incluido.")
    return resultado
