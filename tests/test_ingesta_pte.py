"""Prueba de integración sobre los 36 archivos reales: fija las cifras del diagnóstico (Cap. IV).

Si estas cifras cambian, cambió el código o los datos: hay que revisar la tesis.
"""
import pytest

from asistente.config import RAIZ
from asistente.ingesta.pte import construir_ordenes

pytestmark = pytest.mark.datos

if not any((RAIZ / "data" / "raw" / "pte").glob("*/*.xls")):
    pytest.skip("Faltan los archivos del PTE en data/raw/pte", allow_module_level=True)


@pytest.fixture(scope="module")
def resultado():
    return construir_ordenes(clave_seudonimo="clave-de-prueba")


def test_cifras_de_poblacion(resultado):
    o = resultado.ordenes
    assert len(resultado.manifiesto) == 36
    assert len(o) == 10624
    assert int(o.deviene_seleccion.sum()) == 112
    assert int(o.incluida.sum()) == 10512
    assert int((o.incluida & (o.estado != "anulada")).sum()) == 10467


def test_cobertura_del_codigo(resultado):
    inc = resultado.ordenes[resultado.ordenes.incluida]
    assert round(inc.con_codigo.mean() * 100, 1) == 79.2
    assert inc.codigo_finalidad.nunique() == 216


def test_tramo_sin_codigo_coincide_con_r05(resultado):
    o = resultado.ordenes
    fuera = o[o.estado_confiable]
    dentro = o[~o.estado_confiable]
    assert dentro.con_codigo.sum() == 0              # ago-2024 a mar-2025: ningún código
    assert fuera.con_codigo.mean() > 0.995           # resto: casi todas con código
    assert set(dentro.anio.astype(str) + "-" + dentro.mes.astype(str).str.zfill(2)) == {
        "2024-08", "2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02", "2025-03"}


def test_privacidad(resultado):
    o = resultado.ordenes
    pn = o[o.persona_natural]
    assert pn.ruc_proveedor.str.startswith("PN-").all()
    assert pn.razon_social.isna().all()
    assert not o.ruc_proveedor.str.match(r"^(10|15|17)\d{9}$").any()


def test_sin_duplicados(resultado):
    o = resultado.ordenes
    assert not o.duplicated(["tipo_orden", "numero_orden", "anio"]).any()
    assert o.id_registro.is_unique
