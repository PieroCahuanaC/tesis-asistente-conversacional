"""Criterio de corrección (3.5.3): tolerancia numérica y listas sin orden."""
import pytest

from asistente.evaluacion.comparar import resultados_equivalentes, valores_iguales


@pytest.mark.parametrize("a, b, esperado", [
    (1452526.89, 1452526.89, True),
    (1452527.80, 1452526.89, True),        # diferencia < S/ 1
    (100.0, 100.4, True),                   # 0,4 % < 0,5 %
    (1000.0, 1010.0, False),                # 1 % > 0,5 % y > S/ 1
    ("1452526.89", 1452526.89, True),       # texto numérico
    ("0006508", "0006508", True),
    ("0006508", "0000888", False),
    ("Alcanza", "alcanza", True),
    (None, None, True),
    (None, 0, False),
])
def test_valores_iguales(a, b, esperado):
    assert valores_iguales(a, b) is esperado


def test_lista_sin_orden_y_numerico_con_orden():
    r1 = [["0000888", 10.0], ["0006508", 20.0]]
    r2 = [["0006508", 20.0], ["0000888", 10.0]]
    assert resultados_equivalentes(r1, r2, "lista")
    assert not resultados_equivalentes(r1, r2, "numerico")
    assert not resultados_equivalentes(r1, r1[:1], "lista")
