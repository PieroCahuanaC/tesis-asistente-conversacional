"""Registro de herramientas de C3 (Tabla 11): nombre -> (función, esquema JSON para el modelo)."""
from __future__ import annotations

import time

import psycopg

from asistente.bitacora.registro import Paso
from asistente.herramientas import ordenes, presupuesto

HERRAMIENTAS = {
    "buscar_meta": (presupuesto.buscar_meta, presupuesto.ESQUEMAS["buscar_meta"]),
    "consultar_saldo": (presupuesto.consultar_saldo, presupuesto.ESQUEMAS["consultar_saldo"]),
    "consultar_ejecucion": (presupuesto.consultar_ejecucion, presupuesto.ESQUEMAS["consultar_ejecucion"]),
    "agregar_ordenes": (ordenes.agregar_ordenes, ordenes.ESQUEMA),
    "ranking_metas": (presupuesto.ranking_metas, presupuesto.ESQUEMAS["ranking_metas"]),
    "alertas_ejecucion": (presupuesto.alertas_ejecucion, presupuesto.ESQUEMAS["alertas_ejecucion"]),
    "evaluar_requerimiento": (presupuesto.evaluar_requerimiento, presupuesto.ESQUEMAS["evaluar_requerimiento"]),
}


def esquemas() -> list[dict]:
    return [esquema for _, esquema in HERRAMIENTAS.values()]


def invocar(conn: psycopg.Connection, nombre: str, argumentos: dict) -> Paso:
    """Ejecuta una herramienta pedida por el modelo y devuelve el paso listo para la bitácora."""
    inicio = time.perf_counter()
    if nombre not in HERRAMIENTAS:
        return Paso(tipo="herramienta", nombre=nombre, entrada=argumentos, ok=False,
                    resultado={"disponible": False, "motivo": f"Herramienta inexistente: {nombre}"},
                    error="herramienta inexistente", tiempo_s=time.perf_counter() - inicio)
    funcion, esquema = HERRAMIENTAS[nombre]
    permitidos = set(esquema["function"]["parameters"]["properties"])
    extra = set(argumentos) - permitidos
    if extra:
        return Paso(tipo="herramienta", nombre=nombre, entrada=argumentos, ok=False,
                    resultado={"disponible": False, "motivo": f"Parámetros no reconocidos: {sorted(extra)}"},
                    error="parámetros inválidos", tiempo_s=time.perf_counter() - inicio)
    try:
        resultado = funcion(conn, **argumentos)
        return Paso(tipo="herramienta", nombre=nombre, entrada=argumentos, resultado=resultado,
                    ok=True, tiempo_s=time.perf_counter() - inicio)
    except TypeError as e:  # faltan parámetros obligatorios
        return Paso(tipo="herramienta", nombre=nombre, entrada=argumentos, ok=False,
                    resultado={"disponible": False, "motivo": str(e)}, error=str(e),
                    tiempo_s=time.perf_counter() - inicio)
