"""Ingesta del MEF: fija los totales anuales de Uchumayo y las reglas de la vista de saldo."""
import os

import pytest

from asistente.config import RAIZ, ajustes

pytestmark = pytest.mark.datos

if not all((RAIZ / p).exists() for p in ajustes()["mef"]["archivos"].values()):
    pytest.skip("Faltan los CSV filtrados del MEF (scripts/filtrar_mef.py)", allow_module_level=True)

from asistente.ingesta.mef import construir_ejecucion  # noqa: E402


@pytest.fixture(scope="module")
def r():
    return construir_ejecucion()


def test_totales_anuales(r):
    t = r.ejecucion.groupby("anio")[["pia", "pim"]].sum()
    assert float(t.loc[2023, "pim"]) == 100_195_377
    assert float(t.loc[2024, "pim"]) == 90_088_052
    assert float(t.loc[2025, "pim"]) == 97_749_664
    assert float(t.loc[2025, "pia"]) == 72_475_438


def test_marco_solo_en_mes_cero(r):
    e = r.ejecucion
    assert (e[e.mes > 0][["pia", "pim"]] == 0).all().all()
    assert (e[e.mes == 0][["certificado", "devengado"]] == 0).all().all()


def test_certificacion_no_supera_pim(r):
    t = r.ejecucion.groupby("anio")[["pim", "certificado"]].sum()
    assert (t.certificado <= t.pim).all()
    assert not r.advertencias


def test_finalidades(r):
    assert r.ejecucion.finalidad.str.fullmatch(r"\d{7}").all()
    assert r.ejecucion.groupby("anio").finalidad.nunique().to_dict() == {2023: 146, 2024: 162, 2025: 150}
    assert r.finalidades.finalidad.is_unique
    assert set(r.finalidades.tipo_gasto) <= {"corriente", "inversion"}


@pytest.mark.db
def test_vista_saldo_ejemplo_tesis():
    """Ejemplo T1 de la Tabla 4: saldo de la meta 0006508 al cierre de junio de 2025."""
    if not os.getenv("DATABASE_URL_RO"):
        pytest.skip("DATABASE_URL_RO no configurada")
    from asistente.db.conexion import conectar_ro
    with conectar_ro() as c:
        fila = c.execute("SELECT pim, certificado_acum, saldo FROM datos.v_finalidad_mes "
                         "WHERE anio = 2025 AND mes = 6 AND finalidad = '0006508'").fetchone()
        if fila is None:
            pytest.fail("Ejecute 'python scripts/cargar_mef.py --fecha-corte AAAA-MM-DD' antes de las pruebas")
        pim, cert, saldo = map(float, fila)
        assert pim == 4_137_915.00
        assert cert == pytest.approx(2_685_388.11, abs=0.005)
        assert saldo == pytest.approx(pim - cert, abs=0.005)
        # Al cierre de diciembre el saldo de la vista coincide con PIM - certificación anual.
        anual = c.execute("SELECT sum(pim) - sum(certificado) FROM datos.ejecucion_presupuestal "
                          "WHERE anio = 2025 AND finalidad = '0006508'").fetchone()[0]
        dic = c.execute("SELECT saldo FROM datos.v_finalidad_mes WHERE anio = 2025 AND mes = 12 "
                        "AND finalidad = '0006508'").fetchone()[0]
        assert dic == anual
