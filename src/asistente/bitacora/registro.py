"""Bitácora del sistema (Ficha 4, RF-19, RNF-01, RNF-11).

Cada ejecución guarda la configuración, el modelo, la huella de las instrucciones, el commit del
código, la carga de datos consultada, y cada paso (SQL o herramienta) con el resultado exacto que
vio el modelo. Así toda cifra de una respuesta puede contrastarse con su sustento.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

import psycopg

from asistente.config import commit_actual


def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def carga_vigente(conn: psycopg.Connection) -> tuple[int | None, date | None]:
    """Última carga de datos (id y fecha de corte) que respalda las respuestas."""
    fila = conn.execute("SELECT id_carga, fecha_corte FROM datos.carga "
                        "ORDER BY id_carga DESC LIMIT 1").fetchone()
    return (fila[0], fila[1]) if fila else (None, None)


@dataclass
class Paso:
    tipo: str                    # 'sql' | 'herramienta'
    entrada: dict
    resultado: dict | None
    ok: bool
    nombre: str | None = None
    filas: int | None = None
    error: str | None = None
    tiempo_s: float | None = None


@dataclass
class Ejecucion:
    usuario: str
    configuracion: str
    proveedor: str
    modelo_version: str
    prompt_sha256: str
    pregunta: str
    temperatura: float | None = None
    semilla: int | None = None
    modelo_reportado: str | None = None
    id_pregunta: str | None = None
    repeticion: int | None = None
    respuesta: str | None = None
    abstencion: bool | None = None
    tiempo_s: float | None = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    fecha_corte_datos: date | None = None
    id_carga: int | None = None
    error: str | None = None
    lote: str | None = None
    pasos: list[Paso] = field(default_factory=list)


def registrar(conn: psycopg.Connection, e: Ejecucion) -> str:
    with conn.transaction():
        id_ejecucion = conn.execute(
            """INSERT INTO auditoria.bitacora
               (usuario, configuracion, proveedor, modelo_version, modelo_reportado, temperatura,
                semilla, prompt_sha256, id_pregunta, repeticion, pregunta, respuesta, abstencion,
                tiempo_s, tokens_entrada, tokens_salida, costo_usd, fecha_corte_datos, id_carga,
                commit_codigo, error, lote)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id_ejecucion""",
            (e.usuario, e.configuracion, e.proveedor, e.modelo_version, e.modelo_reportado,
             e.temperatura, e.semilla, e.prompt_sha256, e.id_pregunta, e.repeticion, e.pregunta,
             e.respuesta, e.abstencion, e.tiempo_s, e.tokens_entrada, e.tokens_salida, e.costo_usd,
             e.fecha_corte_datos, e.id_carga, commit_actual(), e.error, e.lote),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO auditoria.bitacora_paso
                   (id_ejecucion, orden, tipo, nombre, entrada, resultado, filas, ok, error, tiempo_s)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [(id_ejecucion, i, p.tipo, p.nombre, json.dumps(p.entrada, ensure_ascii=False, default=str),
                  json.dumps(p.resultado, ensure_ascii=False, default=str) if p.resultado is not None else None,
                  p.filas, p.ok, p.error, p.tiempo_s) for i, p in enumerate(e.pasos, start=1)],
            )
    return str(id_ejecucion)
