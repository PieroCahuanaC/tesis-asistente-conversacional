"""El doble cálculo del solucionario: A (SQL sobre la base) y B (pandas sobre los archivos) deben coincidir."""
import pandas as pd
import pytest

from asistente.config import RAIZ
from asistente.evaluacion import calculo_a as A
from asistente.evaluacion import calculo_b as B
from asistente.evaluacion.comparar import resultados_equivalentes
from asistente.evaluacion.familias import INTERPRETACION, clasificar

BANCO = RAIZ / "eval" / "banco" / "banco_preguntas.xlsx"


def _banco():
    return pd.read_excel(BANCO, sheet_name="Banco")


def test_todas_las_familias_tienen_interpretacion_y_sql():
    for _, r in _banco().iterrows():
        f = clasificar(r.Pregunta, r.Tipo, r.Criterio)
        assert f.nombre in INTERPRETACION
        if f.nombre != "no_respondible":
            f.p.setdefault("fin", "0000000")
            assert A.sql(f).lstrip().upper().startswith(("SELECT", "WITH"))
            assert set(A.COLUMNAS) >= {f.nombre}


@pytest.mark.db
@pytest.mark.datos
def test_a_y_b_coinciden_en_todo_el_banco():
    from asistente.db.conexion import conectar_ro
    from asistente.sql_guard.ejecutor import ejecutar
    distintas = []
    with conectar_ro() as conn:
        for _, r in _banco().iterrows():
            f = clasificar(r.Pregunta, r.Tipo, r.Criterio)
            if f.nombre == "no_respondible":
                continue
            if "nombre" in f.p:
                f.p["fin"] = B.resolver_nombre(f.p["nombre"], f.p.get("anio") or f.p.get("a1"))
            ra = ejecutar(A.sql(f), conn)
            assert ra.ok, (r.ID, ra.error)
            if not resultados_equivalentes(ra.filas, B.calcular(f), r.Criterio):
                distintas.append(r.ID)
    assert distintas == []


@pytest.mark.datos
def test_meta_sin_devengado_aparece_con_cero_en_menor_avance():
    """Caso P177: una finalidad con PIM y sin devengado tiene 0 % de avance (en SQL, NULL quedaba al final)."""
    from asistente.evaluacion.familias import Familia
    filas = B.calcular(Familia("bottom_avance", {"anio": 2024, "n": 5}))
    assert filas[0][1] == 0.0
