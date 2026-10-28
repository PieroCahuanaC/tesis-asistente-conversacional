"""RNF-02: el 100 % de los intentos de modificación debe quedar bloqueado.

Dos niveles: (1) el validador sintáctico, sin base de datos; (2) el rol asistente_ro en
PostgreSQL, aun cuando una sentencia lograra saltarse el validador (defensa en profundidad).
"""
import os

import psycopg
import pytest

from asistente.sql_guard.validador import validar

ATAQUES = [
    "INSERT INTO datos.orden (id_registro) VALUES ('x')",
    "UPDATE datos.orden SET monto_soles = 0",
    "DELETE FROM datos.orden",
    "DROP TABLE datos.orden",
    "TRUNCATE datos.orden",
    "CREATE TABLE datos.x (a int)",
    "ALTER TABLE datos.orden ADD COLUMN x int",
    "GRANT ALL ON datos.orden TO PUBLIC",
    "COPY datos.orden TO '/tmp/x.csv'",
    "SELECT * INTO datos.copia FROM datos.orden",
    "WITH borrado AS (DELETE FROM datos.orden RETURNING *) SELECT * FROM borrado",
    "SELECT 1; DROP TABLE datos.orden",
    "SELECT 1; -- comentario\nDELETE FROM datos.orden",
    "SELECT pg_sleep(10)",
    "SELECT set_config('default_transaction_read_only', 'off', false)",
    "SET default_transaction_read_only = off",
    "BEGIN",
    "SELECT * FROM eval.pregunta",
    "SELECT valor_referencia FROM eval.pregunta WHERE id_pregunta = 'P001'",
    "SELECT * FROM auditoria.bitacora",
    "SELECT * FROM pg_catalog.pg_roles",
    "SELECT * FROM information_schema.tables",
    "SELECT nextval('datos.carga_id_carga_seq')",
    "VACUUM datos.orden",
    "EXPLAIN ANALYZE DELETE FROM datos.orden",
    "",
]

PERMITIDAS = [
    "SELECT count(*) FROM datos.orden WHERE incluida AND anio = 2025 AND mes = 3",
    "SELECT codigo_finalidad, sum(monto_soles) FROM orden GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
    "WITH t AS (SELECT anio, sum(monto_soles) m FROM datos.orden GROUP BY anio) SELECT * FROM t",
    "SELECT o.id_registro, f.nombre_pte FROM datos.orden o JOIN datos.finalidad f USING (codigo_finalidad)",
    "SELECT * FROM generate_series(1, 3)",
]


@pytest.mark.parametrize("sql", ATAQUES)
def test_validador_bloquea(sql):
    assert not validar(sql).permitido


@pytest.mark.parametrize("sql", PERMITIDAS)
def test_validador_permite_lecturas(sql):
    v = validar(sql)
    assert v.permitido, v.motivo


# ---------------------------------------------------------------- nivel 2: PostgreSQL
ESCRITURAS_DIRECTAS = [
    "INSERT INTO datos.finalidad (codigo_finalidad) VALUES ('9999999')",
    "UPDATE datos.orden SET monto_soles = 0",
    "DELETE FROM datos.orden",
    "DROP TABLE datos.orden",
    "TRUNCATE datos.orden",
    "CREATE TABLE datos.x (a int)",
    "SET default_transaction_read_only = off; INSERT INTO datos.finalidad (codigo_finalidad) VALUES ('9999998')",
    "SELECT * FROM eval.pregunta",
    "SELECT * FROM auditoria.bitacora",
]


@pytest.mark.db
@pytest.mark.parametrize("sql", ESCRITURAS_DIRECTAS)
def test_rol_solo_lectura_bloquea_sin_validador(sql):
    url = os.getenv("DATABASE_URL_RO")
    if not url:
        pytest.skip("DATABASE_URL_RO no configurada")
    with psycopg.connect(url, autocommit=True) as c:
        with pytest.raises(psycopg.Error):
            c.execute(sql)


@pytest.mark.db
def test_ejecutor_lee_y_rechaza():
    if not os.getenv("DATABASE_URL_RO"):
        pytest.skip("DATABASE_URL_RO no configurada")
    from asistente.sql_guard.ejecutor import ejecutar
    r = ejecutar("SELECT count(*) AS n FROM datos.orden WHERE incluida")
    assert r.ok and r.columnas == ["n"]
    r = ejecutar("DELETE FROM datos.orden")
    assert not r.ok and "rechazada" in r.error
