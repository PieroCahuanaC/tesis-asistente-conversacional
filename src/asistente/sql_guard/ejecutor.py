"""Ejecutor SQL de solo lectura para C1 y C2: valida, ejecuta con asistente_ro y acota el resultado."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import psycopg

from asistente.config import ajustes
from asistente.db.conexion import conectar_ro
from asistente.sql_guard.validador import validar


@dataclass
class ResultadoSQL:
    ok: bool
    columnas: list[str] = field(default_factory=list)
    filas: list[list] = field(default_factory=list)
    truncado: bool = False
    error: str | None = None
    tiempo_s: float = 0.0

    def como_json(self) -> dict:
        return {"ok": self.ok, "columnas": self.columnas, "filas": self.filas,
                "truncado": self.truncado, "error": self.error}


def _serializable(v):
    if isinstance(v, Decimal):
        return float(v) if v != v.to_integral_value() else int(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def ejecutar(consulta: str, conn: psycopg.Connection | None = None) -> ResultadoSQL:
    cfg = ajustes()["sql"]
    inicio = time.perf_counter()
    veredicto = validar(consulta, tuple(cfg["esquemas_permitidos"]))
    if not veredicto.permitido:
        return ResultadoSQL(ok=False, error=f"Consulta rechazada: {veredicto.motivo}",
                            tiempo_s=time.perf_counter() - inicio)
    propia = conn is None
    conn = conn or conectar_ro()
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = {int(cfg['timeout_ms'])}")
            cur.execute(consulta)
            columnas = [d.name for d in cur.description or []]
            filas = cur.fetchmany(cfg["max_filas"] + 1)
        truncado = len(filas) > cfg["max_filas"]
        filas = [[_serializable(v) for v in f] for f in filas[: cfg["max_filas"]]]
        return ResultadoSQL(True, columnas, filas, truncado, tiempo_s=time.perf_counter() - inicio)
    except psycopg.Error as e:
        return ResultadoSQL(ok=False, error=f"Error de PostgreSQL: {str(e).splitlines()[0]}",
                            tiempo_s=time.perf_counter() - inicio)
    finally:
        if propia:
            conn.close()
