"""Conexiones a PostgreSQL. Dos roles con propósitos distintos:

- admin : crea el esquema, carga los datos y escribe la bitácora.
- ro    : el único que usa el asistente para obtener cifras (C1, C2 y C3).
"""
from __future__ import annotations

import psycopg

from asistente.config import env


def conectar_admin(**kw) -> psycopg.Connection:
    return psycopg.connect(env("DATABASE_URL_ADMIN"), **kw)


def conectar_ro(**kw) -> psycopg.Connection:
    return psycopg.connect(env("DATABASE_URL_RO"), **kw)
