"""Utilidades compartidas por las herramientas de C3: validación de periodos y lecturas de solo lectura."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import psycopg

from asistente.config import ajustes

RE_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
RE_FINALIDAD = re.compile(r"^\d{7}$")
FUENTE_MEF = "Consulta Amigable del MEF (datos abiertos de ejecución del gasto), Municipalidad Distrital de Uchumayo"
FUENTE_PTE = "Portal de Transparencia Estándar, órdenes de compra y de servicio"


class NoDisponible(Exception):
    """La consulta no puede responderse con los datos: la herramienta devuelve disponible=False."""


def no_disponible(motivo: str, **extra) -> dict:
    return {"disponible": False, "motivo": motivo, **extra}


def validar_periodo(periodo: str, nombre: str = "periodo") -> str:
    cfg = ajustes()["periodo"]
    if not isinstance(periodo, str) or not RE_PERIODO.match(periodo):
        raise NoDisponible(f"{nombre} inválido: use el formato AAAA-MM")
    if periodo < cfg["desde"] or periodo > cfg["hasta"]:
        raise NoDisponible(f"Solo hay datos de {cfg['desde']} a {cfg['hasta']}; no se hacen proyecciones")
    return periodo


def validar_rango(desde: str, hasta: str) -> tuple[str, str]:
    validar_periodo(desde, "desde")
    validar_periodo(hasta, "hasta")
    if desde > hasta:
        raise NoDisponible("El mes inicial es posterior al mes final")
    return desde, hasta


def validar_finalidad(codigo: str) -> str:
    if not isinstance(codigo, str) or not RE_FINALIDAD.match(codigo):
        raise NoDisponible("El código de finalidad debe tener 7 dígitos (use buscar_meta si solo conoce el nombre)")
    return codigo


def meses_en_tramo(desde: str, hasta: str) -> list[str]:
    tramo = ajustes()["tramo_sin_codigo_ni_estado"]
    a, m = map(int, desde.split("-"))
    salida = []
    while f"{a:04d}-{m:02d}" <= hasta:
        clave = f"{a:04d}-{m:02d}"
        if tramo["desde"] <= clave <= tramo["hasta"]:
            salida.append(clave)
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida


def leer(conn: psycopg.Connection, consulta: str, parametros: dict | tuple | None = None) -> list[tuple]:
    """Ejecuta una lectura dentro de una transacción de solo lectura."""
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        return conn.execute(consulta, parametros).fetchall()


def fecha_corte(conn: psycopg.Connection, fuente: str) -> str | None:
    fila = leer(conn, "SELECT max(fecha_corte) FROM datos.carga WHERE fuente = %s", (fuente,))[0][0]
    return fila.isoformat() if isinstance(fila, date) else None


def soles(valor) -> float:
    """Redondea a céntimos para la respuesta (los cálculos se hacen en numeric)."""
    return float(Decimal(valor or 0).quantize(Decimal("0.01")))
