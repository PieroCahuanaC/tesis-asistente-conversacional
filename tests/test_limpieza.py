from datetime import date
from decimal import Decimal

import pytest

from asistente.ingesta import limpieza as L


@pytest.mark.parametrize("texto, esperado", [
    ("-0000888 GESTION ADMINISTRATIVA", ("0000888", "GESTION ADMINISTRATIVA")),
    ("- 0006508 MANTENIMIENTO DE PARQUES Y JARDINES", ("0006508", "MANTENIMIENTO DE PARQUES Y JARDINES")),
    ("NO SE NOTIFICO, TODAVIA NO EMPIEZA EL MANTENIMIENTO-0422086  MANTENIMIENTO DE PARQUE",
     ("0422086", "MANTENIMIENTO DE PARQUE")),
    ("SERVICIO DE PEON", (None, None)),                      # tramo ago-2024 a mar-2025
    ("------", (None, None)),
    ("LA PRESENTE ORDEN HACE REFERENCIA A LA ORDEN DE COMPRA 908 DEL AÑO 2023", (None, None)),
    ("COMPRA DE 1234567 UNIDADES", (None, None)),            # 7 dígitos sin guion: no es código
    ("", (None, None)),
])
def test_extraer_finalidad(texto, esperado):
    assert L.extraer_finalidad(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [
    ("S/. 340", Decimal("340")),
    ("S/. 1542.5", Decimal("1542.5")),
    ("S/. 41172.8486", Decimal("41172.8486")),
    ("S/.1,250.00", Decimal("1250.00")),
])
def test_parsear_monto(texto, esperado):
    assert L.parsear_monto(texto) == esperado


@pytest.mark.parametrize("texto", ["1542.5", "US$ 10", "S/. abc"])
def test_parsear_monto_rechaza_formatos_desconocidos(texto):
    with pytest.raises(ValueError):
        L.parsear_monto(texto)


def test_parsear_fecha():
    assert L.parsear_fecha("2023-08-01 00:00:00.0") == date(2023, 8, 1)
    assert L.parsear_fecha("") is None


def test_tipo_contratacion():
    assert L.normalizar_tipo_contratacion(
        "Contrataciones hasta 8 UIT (LEY 30225)((No incluye las derivadas de contrataciones por catálogo electrónico.)"
    ) == "hasta_8_uit"
    assert L.normalizar_tipo_contratacion("Deviene de Procesos de Selección") == "deviene_seleccion"
    assert L.normalizar_tipo_contratacion("NAN") is None


def test_estado():
    assert L.normalizar_estado("Devengada") == "devengada"
    with pytest.raises(ValueError):
        L.normalizar_estado("Pagada")


def test_ruc():
    assert L.normalizar_ruc("20605570870") == "20605570870"
    assert L.normalizar_ruc("20605570870.0") == "20605570870"
    with pytest.raises(ValueError):
        L.normalizar_ruc("123")


def test_seudonimo_estable_e_independiente_de_la_clave():
    a = L.seudonimizar("10413681036", "clave-1")
    assert a == L.seudonimizar("10413681036", "clave-1")
    assert a.startswith("PN-") and len(a) == 15
    assert a != L.seudonimizar("10413681036", "clave-2")
    assert "10413681036" not in a


def test_seudonimo_exige_clave():
    with pytest.raises(RuntimeError):
        L.seudonimizar("10413681036", "CAMBIAR")


def test_en_tramo():
    assert L.en_tramo(2024, 8, "2024-08", "2025-03")
    assert L.en_tramo(2025, 3, "2024-08", "2025-03")
    assert not L.en_tramo(2024, 7, "2024-08", "2025-03")
    assert not L.en_tramo(2025, 4, "2024-08", "2025-03")
