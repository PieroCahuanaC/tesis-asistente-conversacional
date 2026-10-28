"""La herramienta agregar_ordenes debe coincidir con un cálculo independiente en pandas
(mismo principio que la Sección 4.5.1: herramienta vs. consulta de referencia)."""
import os
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.db, pytest.mark.datos]

if not os.getenv("DATABASE_URL_RO"):
    pytest.skip("DATABASE_URL_RO no configurada", allow_module_level=True)

from asistente.db.conexion import conectar_ro  # noqa: E402
from asistente.herramientas.ordenes import agregar_ordenes  # noqa: E402
from asistente.herramientas.registro import invocar  # noqa: E402
from asistente.ingesta.pte import construir_ordenes  # noqa: E402


@pytest.fixture(scope="module")
def conn():
    with conectar_ro() as c:
        if c.execute("SELECT count(*) FROM datos.orden").fetchone()[0] == 0:
            pytest.fail("La base no tiene órdenes cargadas: ejecute "
                        "'python scripts/cargar_pte.py --fecha-corte AAAA-MM-DD' antes de las pruebas")
        yield c


@pytest.fixture(scope="module")
def df():
    # Seudónimos irrelevantes aquí: solo se usan montos, fechas y filtros.
    return construir_ordenes(clave_seudonimo="otra-clave").ordenes


def _referencia(df, desde, hasta, tipo=None, codigo=None, estado=None):
    clave = df.anio.astype(str) + "-" + df.mes.astype(str).str.zfill(2)
    m = df.incluida & clave.between(desde, hasta)
    if tipo:
        m &= df.tipo_orden == tipo
    if codigo:
        m &= df.codigo_finalidad == codigo
    if estado:
        m &= df.estado == estado
    sub = df[m]
    monto = sum(sub[sub.estado != "anulada"].monto_soles, Decimal(0))
    return len(sub), int((sub.estado == "anulada").sum()), float(monto.quantize(Decimal("0.01")))


@pytest.mark.parametrize("args", [
    dict(desde="2025-03", hasta="2025-03", tipo="O/S"),           # ejemplo T3 de la Tabla 4
    dict(desde="2023-01", hasta="2023-12"),
    dict(desde="2023-01", hasta="2025-12"),
    dict(desde="2024-01", hasta="2024-03", codigo="0000888"),
    dict(desde="2025-04", hasta="2025-12", codigo="0006508", tipo="O/C"),
    dict(desde="2023-06", hasta="2023-06", estado="devengada"),
])
def test_coincide_con_referencia(conn, df, args):
    r = agregar_ordenes(conn, args["desde"], args["hasta"], args.get("tipo"), args.get("codigo"), args.get("estado"))
    assert r["disponible"]
    assert (r["conteo_ordenes"], r["conteo_anuladas"], r["monto_total_soles"]) == _referencia(
        df, args["desde"], args["hasta"], args.get("tipo"), args.get("codigo"), args.get("estado"))


@pytest.mark.parametrize("args", [
    dict(desde="2024-10", hasta="2024-10", codigo_finalidad="0000888"),   # tramo sin código
    dict(desde="2024-06", hasta="2024-09", estado="devengada"),           # toca el tramo sin estado
    dict(desde="2026-12", hasta="2026-12"),                               # fuera de los datos (T7)
    dict(desde="2022-12", hasta="2023-01"),
    dict(desde="2025-13", hasta="2025-13"),
    dict(desde="2025-05", hasta="2025-02"),
])
def test_se_abstiene_cuando_no_hay_dato(conn, args):
    r = agregar_ordenes(conn, **args)
    assert r["disponible"] is False and r["motivo"]


def test_advierte_anuladas_no_identificables(conn):
    r = agregar_ordenes(conn, "2024-07", "2024-08")
    assert r["disponible"] and "advertencia" in r


def test_invocar_valida_parametros(conn):
    assert invocar(conn, "agregar_ordenes", {"desde": "2025-03", "hasta": "2025-03"}).ok
    assert not invocar(conn, "agregar_ordenes", {"desde": "2025-03", "hasta": "2025-03", "sql": "x"}).ok
    assert not invocar(conn, "agregar_ordenes", {"desde": "2025-03"}).ok
    assert not invocar(conn, "borrar_todo", {}).ok
