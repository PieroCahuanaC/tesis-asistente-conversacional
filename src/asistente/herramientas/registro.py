"""Registro de herramientas de C3: nombre -> (función, esquema JSON para el modelo).

Las herramientas que dependen de la Consulta Amigable (buscar_meta, consultar_saldo,
consultar_ejecucion, ranking_metas, alertas_ejecucion, evaluar_requerimiento) se agregan
cuando se carguen los datos del MEF.
"""
from __future__ import annotations

import time

import psycopg

from asistente.bitacora.registro import Paso
from asistente.herramientas import ordenes

HERRAMIENTAS = {
    "agregar_ordenes": (ordenes.agregar_ordenes, ordenes.ESQUEMA),
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
