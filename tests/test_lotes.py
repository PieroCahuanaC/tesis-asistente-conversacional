"""Planificación y reanudación de la ejecución por lotes."""
import os

import pytest

from asistente.evaluacion.lotes import (Tarea, es_falla_proveedor, huella_banco, muestra_estratificada,
                                        planificar)

FILAS = [{"id": f"P{i:03d}", "texto": f"pregunta {i}", "tipo": f"T{1 + i % 7}", "ref": [[i]], "criterio": "numerico"}
         for i in range(1, 36)]


def test_cada_pregunta_corre_en_las_tres_configuraciones_seguidas_y_rotadas():
    t = planificar(FILAS, ["C1", "C2", "C3"], 1, 20251231)
    assert len(t) == 105 and len(set(t)) == 105
    primeras = [t[i].configuracion for i in range(0, 105, 3)]
    assert {primeras.count(c) for c in ("C1", "C2", "C3")} == {12, 12, 11} or set(primeras) == {"C1", "C2", "C3"}
    for i in range(0, 105, 3):
        bloque = t[i:i + 3]
        assert len({x.id_pregunta for x in bloque}) == 1 and {x.configuracion for x in bloque} == {"C1", "C2", "C3"}
    assert planificar(FILAS, ["C1", "C2", "C3"], 1, 20251231) == t          # reproducible


def test_repeticiones_y_muestra():
    m = muestra_estratificada(FILAS, 0.2, 20251231)
    assert len(m) == 7 and len({f["tipo"] for f in m}) == 7
    t = planificar(m, ["C3"], 3, 20251231)
    assert len(t) == 21 and {x.repeticion for x in t} == {1, 2, 3}


def test_huella_cambia_si_cambia_una_referencia():
    otra = [dict(f) for f in FILAS]
    otra[0]["ref"] = [[999]]
    assert huella_banco(FILAS) != huella_banco(otra)
    assert huella_banco(FILAS) == huella_banco(list(reversed(FILAS)))


def test_falla_del_proveedor_vs_falla_del_asistente():
    assert es_falla_proveedor("RateLimitError: Error code: 429")
    assert not es_falla_proveedor("Se alcanzó el máximo de 6 pasos sin respuesta final")
    assert not es_falla_proveedor(None)


@pytest.mark.db
def test_lote_se_reanuda_sin_repetir(tmp_path):
    if not (os.getenv("DATABASE_URL_RO") and os.getenv("DATABASE_URL_ADMIN")):
        pytest.skip("Base de datos no configurada")
    from asistente.db.conexion import conectar_admin, conectar_ro
    from asistente.evaluacion.lotes import completadas
    from asistente.llm.base import RespuestaLLM
    from asistente.orquestador import responder

    class Fijo:
        proveedor, modelo, temperatura, semilla = "simulado", "fijo", 0, 1

        def __init__(self, error=None):
            self.error = error

        def generar(self, mensajes, herramientas=None):
            if self.error:
                raise RuntimeError(self.error)
            return RespuestaLLM(texto="[ABSTENCIÓN] prueba", llamadas=[], tokens_entrada=1, tokens_salida=1,
                                modelo_reportado="fijo", mensaje_crudo={"role": "assistant", "content": "x"})

    with conectar_admin() as a, conectar_ro() as r:
        pid = a.execute("SELECT id_pregunta FROM eval.pregunta LIMIT 1").fetchone()
        if pid is None:
            pytest.skip("Banco no cargado (scripts/cargar_banco.py)")
        a.execute("""INSERT INTO eval.lote (nombre, conjunto, configuraciones, banco_sha256, modelo, proveedor, commit_inicio)
                     VALUES ('pytest', 'prueba', '{C1}', 'x', 'fijo', 'simulado', 'x') ON CONFLICT DO NOTHING""")
        a.commit()
        try:
            responder("¿?", "C1", Fijo("429 límite"), a, r, usuario="pytest", id_pregunta=pid[0], repeticion=1, lote="pytest")
            assert completadas(a, "pytest") == set()                        # falla del proveedor: queda pendiente
            responder("¿?", "C1", Fijo(), a, r, usuario="pytest", id_pregunta=pid[0], repeticion=1, lote="pytest")
            assert completadas(a, "pytest") == {(pid[0], "C1", 1)}
        finally:
            a.execute("DELETE FROM auditoria.bitacora WHERE lote = 'pytest'")
            a.execute("DELETE FROM eval.lote WHERE nombre = 'pytest'")
            a.commit()
