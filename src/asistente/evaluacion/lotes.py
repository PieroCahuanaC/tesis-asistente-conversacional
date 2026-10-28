"""Ejecución por lotes del banco de preguntas (etapas 3 y 5 de 3.5.4; RF-20).

Un lote es una corrida identificada (piloto, principal, estabilidad). Cada (pregunta, configuración,
repetición) se ejecuta una sola vez dentro del lote: si el proceso se corta, se retoma donde quedó.
Las fallas del proveedor (límite de tokens, red) no cuentan como respuesta y se reintentan; el
máximo de pasos sin respuesta sí es una respuesta (fallida) del asistente.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import dataclass

import psycopg

from asistente.orquestador import ERROR_MAX_PASOS


@dataclass(frozen=True)
class Tarea:
    id_pregunta: str
    texto: str
    configuracion: str
    repeticion: int


def preguntas(conn: psycopg.Connection, conjunto: str, ids: list[str] | None = None) -> list[dict]:
    q = ("SELECT id_pregunta, texto, tipo_consulta, valor_referencia, criterio FROM eval.pregunta "
         "WHERE conjunto = %s ORDER BY id_pregunta")
    filas = [dict(zip(("id", "texto", "tipo", "ref", "criterio"), f)) for f in conn.execute(q, (conjunto,)).fetchall()]
    if ids:
        filas = [f for f in filas if f["id"] in set(ids)]
    return filas


def huella_banco(filas: list[dict]) -> str:
    """sha256 de preguntas, referencias y criterios: si cambian, el lote ya no es comparable."""
    canon = [[f["id"], f["texto"], f["ref"], f["criterio"]] for f in sorted(filas, key=lambda x: x["id"])]
    return hashlib.sha256(json.dumps(canon, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def muestra_estratificada(filas: list[dict], fraccion: float, semilla: int) -> list[dict]:
    """Fracción de preguntas por tipo (T1..T7), reproducible con la semilla del estudio."""
    por_tipo = defaultdict(list)
    for f in filas:
        por_tipo[f["tipo"]].append(f)
    rng = random.Random(semilla)
    elegidas = []
    for tipo in sorted(por_tipo):
        grupo = sorted(por_tipo[tipo], key=lambda x: x["id"])
        elegidas += rng.sample(grupo, max(1, round(fraccion * len(grupo))))
    return sorted(elegidas, key=lambda x: x["id"])


def planificar(filas: list[dict], configuraciones: list[str], repeticiones: int, semilla: int) -> list[Tarea]:
    """Orden aleatorio (fijo por la semilla) de preguntas; para cada pregunta, las configuraciones se
    ejecutan seguidas y en orden rotado, para que ninguna quede siempre primera o última (misma ventana)."""
    rng = random.Random(semilla)
    orden = sorted(filas, key=lambda x: x["id"])
    rng.shuffle(orden)
    tareas = []
    for r in range(1, repeticiones + 1):
        for i, f in enumerate(orden):
            k = i % len(configuraciones)
            for c in configuraciones[k:] + configuraciones[:k]:
                tareas.append(Tarea(f["id"], f["texto"], c, r))
    return tareas


def completadas(conn: psycopg.Connection, lote: str) -> set[tuple[str, str, int]]:
    """Ejecuciones válidas del lote: sin error, o con el error propio del asistente (máximo de pasos)."""
    q = ("SELECT id_pregunta, configuracion, repeticion FROM auditoria.bitacora "
         "WHERE lote = %s AND (error IS NULL OR error LIKE %s)")
    return {tuple(f) for f in conn.execute(q, (lote, ERROR_MAX_PASOS + "%")).fetchall()}


def es_falla_proveedor(error: str | None) -> bool:
    return bool(error) and not error.startswith(ERROR_MAX_PASOS)
