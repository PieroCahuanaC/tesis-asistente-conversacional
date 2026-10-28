"""Criterio de corrección (3.5.3) y script de doble cálculo de referencias."""
import os
import shutil

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


@pytest.mark.db
def test_script_compara_y_marca(tmp_path):
    if not os.getenv("DATABASE_URL_RO"):
        pytest.skip("DATABASE_URL_RO no configurada")
    from openpyxl import load_workbook

    from asistente.config import RAIZ
    origen = RAIZ / "eval" / "banco" / "banco_preguntas.xlsx"
    if not origen.exists():
        pytest.skip("No existe el banco (scripts/generar_banco.py)")
    import importlib.util
    spec = importlib.util.spec_from_file_location("comparar_referencias", RAIZ / "scripts" / "comparar_referencias.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    copia = tmp_path / "banco.xlsx"
    shutil.copy(origen, copia)
    wb = load_workbook(copia)
    ws = wb["Banco"]
    col = {c.value: c.column for c in ws[1]}
    saldo_a = ("SELECT sum(pim) - (SELECT sum(certificado) FROM datos.ejecucion_presupuestal WHERE finalidad='0006508' "
               "AND anio=2025 AND mes BETWEEN 1 AND 6) FROM datos.ejecucion_presupuestal WHERE finalidad='0006508' AND anio=2025")
    saldo_b = "SELECT saldo FROM datos.v_finalidad_mes WHERE finalidad='0006508' AND anio=2025 AND mes=6"
    casos = {2: (saldo_a, saldo_b), 3: (saldo_a, "SELECT 1"), 4: ("NO RESPONDIBLE", "no respondible"),
             5: ("DELETE FROM datos.orden", saldo_b)}
    for fila, (a, b) in casos.items():
        ws.cell(fila, col["Criterio"]).value = "numerico"
        ws.cell(fila, col["SQL_Rodrigo"]).value = a
        ws.cell(fila, col["SQL_Tony"]).value = b
    wb.save(copia)

    conteo = modulo.comparar_archivo(copia)
    ws = load_workbook(copia)["Banco"]
    assert [ws.cell(f, col["Coinciden"]).value for f in (2, 3, 4, 5)] == ["SÍ", "NO", "SÍ", "NO"]
    assert "rechazada" in ws.cell(5, col["Resultado_Rodrigo"]).value
    assert conteo["comparadas"] == 4 and conteo["coinciden"] == 2
