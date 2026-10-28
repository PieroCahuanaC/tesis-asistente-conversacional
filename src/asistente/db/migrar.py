"""Crea (o actualiza) la base: esquemas, tablas, rol de solo lectura, permisos y tabla UIT.

Uso:  python -m asistente.db.migrar
Idempotente: puede ejecutarse cuantas veces se quiera.
"""
from __future__ import annotations

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from asistente.config import RAIZ, ajustes, env

DIR_SQL = RAIZ / "db" / "sql"


def _nombre_bd(url: str) -> str:
    return conninfo_to_dict(url)["dbname"]


def crear_base_si_falta(url_admin: str) -> None:
    nombre = _nombre_bd(url_admin)
    with psycopg.connect(make_conninfo(url_admin, dbname="postgres"), autocommit=True) as c:
        existe = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone()
        if not existe:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
            print(f"Base de datos '{nombre}' creada")


def migrar() -> None:
    url_admin = env("DATABASE_URL_ADMIN")
    crear_base_si_falta(url_admin)
    clave_ro = env("ASISTENTE_RO_PASSWORD")
    with psycopg.connect(url_admin, autocommit=True) as c:
        c.execute((DIR_SQL / "01_esquema.sql").read_text(encoding="utf-8"))

        existe = c.execute("SELECT 1 FROM pg_roles WHERE rolname = 'asistente_ro'").fetchone()
        verbo = "ALTER" if existe else "CREATE"
        c.execute(sql.SQL(verbo + " ROLE asistente_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                          "NOINHERIT CONNECTION LIMIT 20 PASSWORD {}").format(sql.Literal(clave_ro)))
        nombre_bd = _nombre_bd(url_admin)
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO asistente_ro").format(sql.Identifier(nombre_bd)))
        c.execute((DIR_SQL / "02_permisos.sql").read_text(encoding="utf-8"))

        for anio, valor in ajustes()["uit"].items():
            c.execute("INSERT INTO datos.uit (anio, valor) VALUES (%s, %s) "
                      "ON CONFLICT (anio) DO UPDATE SET valor = EXCLUDED.valor", (int(anio), valor))
    print("Migración completada: esquemas datos/eval/auditoria, rol asistente_ro y tabla UIT")


if __name__ == "__main__":
    migrar()
