"""Validador sintáctico del SQL generado por el modelo en C1 y C2 (RF-12, RNF-02).

Es la segunda capa de defensa: la primera es el rol asistente_ro (solo SELECT sobre el
esquema datos y transacciones de solo lectura). Aquí se rechaza, antes de llegar a la base,
todo lo que no sea exactamente UNA consulta de lectura sobre tablas del esquema permitido.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# Funciones con efectos secundarios o que dan acceso fuera de los datos.
_FUNCIONES_PROHIBIDAS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "set_config", "pg_terminate_backend",
    "pg_cancel_backend", "pg_reload_conf", "pg_read_file", "pg_read_binary_file", "pg_ls_dir",
    "pg_stat_file", "lo_import", "lo_export", "lo_unlink", "dblink", "dblink_exec",
    "pg_advisory_lock", "pg_advisory_xact_lock", "nextval", "setval", "txid_current",
    "pg_notify", "query_to_xml", "current_setting", "pg_switch_wal",
}

# Nodos de sqlglot que implican escritura, DDL, permisos o comandos de sesión.
_NODOS_PROHIBIDOS = tuple(getattr(exp, n) for n in (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "TruncateTable",
    "Grant", "Revoke", "Command", "Set", "Copy", "Into", "Transaction", "Commit", "Rollback",
    "LoadData", "Use", "Lock",
) if hasattr(exp, n))


@dataclass(frozen=True)
class Veredicto:
    permitido: bool
    motivo: str = ""


def validar(consulta: str, esquemas_permitidos: tuple[str, ...] = ("datos",)) -> Veredicto:
    texto = (consulta or "").strip()
    if not texto:
        return Veredicto(False, "consulta vacía")
    try:
        sentencias = [s for s in sqlglot.parse(texto, read="postgres") if s is not None]
    except ParseError as e:
        return Veredicto(False, f"SQL no válido: {str(e).splitlines()[0]}")
    if len(sentencias) != 1:
        return Veredicto(False, f"se esperaba una sola sentencia y hay {len(sentencias)}")
    arbol = sentencias[0]

    if not isinstance(arbol, exp.Query):
        return Veredicto(False, f"solo se permite SELECT (se recibió {type(arbol).__name__})")

    for nodo in arbol.walk():
        if isinstance(nodo, _NODOS_PROHIBIDOS):
            return Veredicto(False, f"operación no permitida: {type(nodo).__name__}")
        if isinstance(nodo, exp.Func):
            nombre = (nodo.name if isinstance(nodo, exp.Anonymous) else nodo.sql_name()).lower()
            if nombre in _FUNCIONES_PROHIBIDAS:
                return Veredicto(False, f"función no permitida: {nombre}")

    ctes = {c.alias_or_name.lower() for c in arbol.find_all(exp.CTE)}
    for tabla in arbol.find_all(exp.Table):
        if not tabla.name:          # funciones de tabla como generate_series
            continue
        esquema = (tabla.db or "").lower()
        if not esquema and tabla.name.lower() in ctes:
            continue
        if esquema and esquema not in esquemas_permitidos:
            return Veredicto(False, f"esquema no permitido: {esquema}")
        if esquema.startswith("pg_") or tabla.name.lower().startswith("pg_") or esquema == "information_schema":
            return Veredicto(False, "no se permite consultar el catálogo del sistema")
    return Veredicto(True)
