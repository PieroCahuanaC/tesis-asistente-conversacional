"""Herramientas de C3 sobre el presupuesto: cada una se contrasta con un cálculo independiente en
pandas sobre los CSV del MEF (no con la vista SQL que usa la herramienta). Sección 4.5.1."""
import os
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.db, pytest.mark.datos]

if not os.getenv("DATABASE_URL_RO"):
    pytest.skip("DATABASE_URL_RO no configurada", allow_module_level=True)

from asistente.config import RAIZ, ajustes  # noqa: E402

if not all((RAIZ / p).exists() for p in ajustes()["mef"]["archivos"].values()):
    pytest.skip("Faltan los CSV filtrados del MEF", allow_module_level=True)

from asistente.db.conexion import conectar_ro  # noqa: E402
from asistente.herramientas import presupuesto as P  # noqa: E402
from asistente.herramientas.registro import HERRAMIENTAS, invocar  # noqa: E402
from asistente.ingesta.mef import construir_ejecucion  # noqa: E402


@pytest.fixture(scope="module")
def conn():
    with conectar_ro() as c:
        if c.execute("SELECT count(*) FROM datos.ejecucion_presupuestal").fetchone()[0] == 0:
            pytest.fail("Ejecute 'python scripts/cargar_mef.py --fecha-corte AAAA-MM-DD' antes de las pruebas")
        yield c


@pytest.fixture(scope="module")
def e():
    return construir_ejecucion().ejecucion


def _cent(x) -> float:
    return float(Decimal(x).quantize(Decimal("0.01")))


def _saldo_ref(e, fin, anio, mes):
    d = e[(e.finalidad == fin) & (e.anio == anio)]
    pim = sum(d.pim, Decimal(0))
    cert = sum(d[(d.mes >= 1) & (d.mes <= mes)].certificado, Decimal(0))
    return pim, cert, pim - cert


@pytest.mark.parametrize("fin, periodo", [("0006508", "2025-06"), ("0000888", "2024-03"),
                                          ("0001490", "2025-10"), ("0006508", "2023-12")])
def test_consultar_saldo(conn, e, fin, periodo):
    anio, mes = map(int, periodo.split("-"))
    pim, cert, saldo = _saldo_ref(e, fin, anio, mes)
    r = P.consultar_saldo(conn, codigo_finalidad=fin, periodo=periodo)
    assert r["disponible"]
    assert (r["pim"], r["certificado_acumulado"], r["saldo"]) == (_cent(pim), _cent(cert), _cent(saldo))


def test_ejemplos_de_la_tabla_4(conn):
    assert P.consultar_saldo(conn, codigo_finalidad="0006508", periodo="2025-06")["saldo"] == 1_452_526.89
    r = P.evaluar_requerimiento(conn, codigo_finalidad="0001490", monto=12000, periodo="2025-10")
    assert r["resultado"] == "alcanza" and r["diferencia"] == round(r["saldo_disponible"] - 12000, 2)


@pytest.mark.parametrize("monto, esperado", [(1, "alcanza"), (10_000_000, "no alcanza")])
def test_evaluar_requerimiento(conn, monto, esperado):
    assert P.evaluar_requerimiento(conn, codigo_finalidad="0006508", monto=monto, periodo="2025-06")["resultado"] == esperado


def test_consultar_ejecucion(conn, e):
    d = e[(e.finalidad == "0000888") & (e.anio == 2024) & e.mes.between(1, 3)]
    r = P.consultar_ejecucion(conn, desde="2024-01", hasta="2024-03", codigo_finalidad="0000888")
    assert r["comprometido"] == _cent(sum(d.comprometido_anual, Decimal(0)))
    assert r["devengado"] == _cent(sum(d.devengado, Decimal(0)))
    assert r["certificado"] == _cent(sum(d.certificado, Decimal(0)))
    assert r["monto_ordenes_8uit"] is not None


def test_consultar_ejecucion_varios_anios_toda_la_municipalidad(conn, e):
    d = e[(e.mes > 0) & (((e.anio == 2023) & (e.mes >= 11)) | ((e.anio == 2024) & (e.mes <= 2)))]
    r = P.consultar_ejecucion(conn, desde="2023-11", hasta="2024-02")
    assert r["devengado"] == _cent(sum(d.devengado, Decimal(0)))


def test_ordenes_no_disponibles_en_tramo_por_meta(conn):
    r = P.consultar_ejecucion(conn, desde="2024-07", hasta="2024-09", codigo_finalidad="0000888")
    assert r["disponible"] and r["monto_ordenes_8uit"] is None and "advertencia_ordenes" in r


def test_ranking_devengado(conn, e):
    d = e[(e.anio == 2023) & (e.mes > 0)].groupby("finalidad").devengado.sum().sort_values(ascending=False)
    r = P.ranking_metas(conn, anio=2023, criterio="devengado", n=5)
    assert [x["codigo_finalidad"] for x in r["ranking"]] == list(d.index[:5])
    assert r["ranking"][0]["valor"] == _cent(d.iloc[0])


def test_alertas(conn, e):
    anio, mes, umbral = 2025, 9, 80
    d = e[e.anio == anio]
    pim = d.groupby("finalidad").pim.sum()
    dev = d[(d.mes >= 1) & (d.mes <= mes)].groupby("finalidad").devengado.sum().reindex(pim.index, fill_value=0)
    avance = (dev.astype(float) / pim.astype(float) * 100).round(2)
    esperado = set(avance[(pim > 0) & (avance > umbral)].index)
    r = P.alertas_ejecucion(conn, periodo="2025-09", umbral_pct=80)
    assert {m["codigo_finalidad"] for m in r["metas"]} == esperado and r["cantidad"] == len(esperado)


def test_buscar_meta(conn):
    r = P.buscar_meta(conn, texto="parques y jardines")
    assert "0006508" in [c["codigo_finalidad"] for c in r["coincidencias"]]
    assert P.buscar_meta(conn, texto="GESTIÓN ADMINISTRATIVA")["coincidencias"][0]["codigo_finalidad"] == "0000888"


@pytest.mark.parametrize("nombre, args", [
    ("consultar_saldo", {"codigo_finalidad": "0006508", "periodo": "2026-12"}),     # predicción (T7)
    ("consultar_saldo", {"codigo_finalidad": "9999999", "periodo": "2025-06"}),     # meta inexistente
    ("consultar_saldo", {"codigo_finalidad": "888", "periodo": "2025-06"}),
    ("evaluar_requerimiento", {"codigo_finalidad": "0006508", "monto": -5, "periodo": "2025-06"}),
    ("ranking_metas", {"anio": 2024, "criterio": "monto_ordenes"}),               # tramo sin código
    ("ranking_metas", {"anio": 2022, "criterio": "devengado"}),
    ("alertas_ejecucion", {"periodo": "2025-09", "umbral_pct": 150}),
    ("buscar_meta", {"texto": "zz"}),
    ("buscar_meta", {"texto": "helicoptero espacial"}),
    ("consultar_ejecucion", {"desde": "2025-06", "hasta": "2025-01"}),
])
def test_abstencion(conn, nombre, args):
    paso = invocar(conn, nombre, args)
    assert paso.ok and paso.resultado["disponible"] is False and paso.resultado["motivo"]


def test_registro_completo():
    assert set(HERRAMIENTAS) == {"buscar_meta", "consultar_saldo", "consultar_ejecucion", "agregar_ordenes",
                                 "ranking_metas", "alertas_ejecucion", "evaluar_requerimiento"}
    for nombre, (_, esquema) in HERRAMIENTAS.items():
        assert esquema["function"]["name"] == nombre
