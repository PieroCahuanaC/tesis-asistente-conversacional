"""Bucle del orquestador con un modelo simulado (sin red): herramientas, SQL, abstención y bitácora."""
import os

import pytest

from asistente.llm.base import LlamadaHerramienta, RespuestaLLM

pytestmark = pytest.mark.db

if not (os.getenv("DATABASE_URL_RO") and os.getenv("DATABASE_URL_ADMIN")):
    pytest.skip("Base de datos no configurada", allow_module_level=True)

from asistente.db.conexion import conectar_admin, conectar_ro  # noqa: E402
from asistente.orquestador import MARCA_ABSTENCION, construir_contexto, responder  # noqa: E402


class ModeloGuionado:
    """Devuelve respuestas predefinidas y guarda lo que recibió."""
    proveedor, modelo, temperatura, semilla = "simulado", "guion", 0, 1

    def __init__(self, guion):
        self.guion = list(guion)
        self.recibido = []

    def generar(self, mensajes, herramientas=None):
        self.recibido.append((list(mensajes), herramientas))
        texto, llamadas = self.guion.pop(0)
        crudo = {"role": "assistant", "content": texto}
        if llamadas:
            crudo["tool_calls"] = [{"id": l.id, "type": "function",
                                    "function": {"name": l.nombre, "arguments": "{}"}} for l in llamadas]
        return RespuestaLLM(texto=texto, llamadas=llamadas, tokens_entrada=100, tokens_salida=10,
                            modelo_reportado="guion-1", mensaje_crudo=crudo)


@pytest.fixture(scope="module")
def conns():
    with conectar_admin() as a, conectar_ro() as r:
        yield a, r


def _limpiar(admin, id_ejecucion):
    admin.execute("DELETE FROM auditoria.bitacora WHERE id_ejecucion = %s", (id_ejecucion,))
    admin.commit()


def test_c3_usa_herramienta_y_registra(conns):
    admin, ro = conns
    modelo = ModeloGuionado([
        (None, [LlamadaHerramienta("c1", "consultar_saldo", {"codigo_finalidad": "0006508", "periodo": "2025-06"})]),
        ("El saldo es S/ 1 452 526,89. Fuente: Consulta Amigable del MEF.", []),
    ])
    r = responder("¿Saldo de 0006508 a junio de 2025?", "C3", modelo, admin, ro, usuario="pytest")
    assert not r.abstencion and r.error is None
    assert r.pasos[0].resultado["saldo"] == 1_452_526.89
    assert (r.tokens_entrada, r.tokens_salida) == (200, 20)
    # El resultado de la herramienta se devolvió al modelo como mensaje 'tool'.
    ultimo = modelo.recibido[-1][0][-1]
    assert ultimo["role"] == "tool" and "1452526.89" in ultimo["content"]
    fila = admin.execute("SELECT configuracion, abstencion, tokens_entrada FROM auditoria.bitacora "
                         "WHERE id_ejecucion = %s", (r.id_ejecucion,)).fetchone()
    assert fila == ("C3", False, 200)
    assert admin.execute("SELECT count(*) FROM auditoria.bitacora_paso WHERE id_ejecucion = %s",
                         (r.id_ejecucion,)).fetchone()[0] == 1
    _limpiar(admin, r.id_ejecucion)


def test_c1_ejecuta_sql_y_bloquea_escritura(conns):
    admin, ro = conns
    modelo = ModeloGuionado([
        (None, [LlamadaHerramienta("a", "ejecutar_sql", {"consulta": "DELETE FROM datos.orden"})]),
        (None, [LlamadaHerramienta("b", "ejecutar_sql", {"consulta": "SELECT count(*) FROM datos.orden WHERE incluida"})]),
        ("Hay 10 512 órdenes.", []),
    ])
    r = responder("¿Cuántas órdenes hay?", "C1", modelo, admin, ro, usuario="pytest")
    assert not r.pasos[0].ok and "rechazada" in r.pasos[0].error
    assert r.pasos[1].ok and r.pasos[1].resultado["filas"] == [[10512]]
    _limpiar(admin, r.id_ejecucion)


def test_abstencion_detectada(conns):
    admin, ro = conns
    modelo = ModeloGuionado([(f"{MARCA_ABSTENCION} No hay datos de 2026.", [])])
    r = responder("¿Cuánto se gastará en diciembre de 2026?", "C3", modelo, admin, ro, usuario="pytest")
    assert r.abstencion and not r.pasos
    _limpiar(admin, r.id_ejecucion)


def test_limite_de_pasos(conns):
    admin, ro = conns
    llamada = LlamadaHerramienta("x", "buscar_meta", {"texto": "parques"})
    modelo = ModeloGuionado([(None, [llamada])] * 10)
    r = responder("bucle", "C3", modelo, admin, ro, usuario="pytest")
    assert r.error and "máximo" in r.error and r.abstencion
    _limpiar(admin, r.id_ejecucion)


def test_contextos_diferenciados(conns):
    admin, _ = conns
    s1, t1 = construir_contexto(admin, "C1")
    s2, t2 = construir_contexto(admin, "C2")
    s3, t3 = construir_contexto(admin, "C3")
    assert [t["function"]["name"] for t in t1] == ["ejecutar_sql"] == [t["function"]["name"] for t in t2]
    assert len(t3) == 7 and "ejecutar_sql" not in s3
    assert "datos.orden" in s1 and "--" not in s1.split("Esquema")[1]          # C1 sin descripciones
    assert "Diccionario semántico" in s2 and "--" in s2                        # C2 con descripciones
    assert "eval." not in s1 + s2 and "auditoria." not in s1 + s2             # nunca expone el banco
