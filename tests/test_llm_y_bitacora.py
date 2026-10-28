"""Adaptador del LLM con un cliente simulado (sin red) y escritura en la bitácora."""
import json
import os
from types import SimpleNamespace as NS

import pytest

from asistente.llm.base import costo_usd, crear_modelo


class ClienteFalso:
    def __init__(self, respuesta):
        self.recibido = None
        self._respuesta = respuesta
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.recibido = kw
        return self._respuesta


def _respuesta(tool_calls=None, content=None):
    msg = NS(content=content, tool_calls=tool_calls)
    return NS(choices=[NS(message=msg, finish_reason="tool_calls" if tool_calls else "stop")],
              usage=NS(prompt_tokens=1200, completion_tokens=80), model="openai/gpt-oss-120b")


def test_parametros_reproducibles_y_llamada_a_herramienta():
    tc = NS(id="call_1", function=NS(name="agregar_ordenes",
                                     arguments=json.dumps({"desde": "2025-03", "hasta": "2025-03"})))
    cliente = ClienteFalso(_respuesta(tool_calls=[tc]))
    cfg = {"proveedor": "groq", "modelo": "openai/gpt-oss-120b", "temperatura": 0, "semilla": 7,
           "esfuerzo_razonamiento": "low", "max_tokens_salida": 512}
    modelo = crear_modelo(cfg, cliente=cliente)
    r = modelo.generar([{"role": "user", "content": "hola"}], herramientas=[{"type": "function"}])

    assert cliente.recibido["temperature"] == 0
    assert cliente.recibido["seed"] == 7
    assert cliente.recibido["reasoning_effort"] == "low"
    assert cliente.recibido["tool_choice"] == "auto"
    assert r.llamadas[0].nombre == "agregar_ordenes"
    assert r.llamadas[0].argumentos == {"desde": "2025-03", "hasta": "2025-03"}
    assert (r.tokens_entrada, r.tokens_salida) == (1200, 80)
    assert r.mensaje_crudo["tool_calls"][0]["id"] == "call_1"


def test_argumentos_invalidos_no_rompen():
    tc = NS(id="c", function=NS(name="agregar_ordenes", arguments="{no es json"))
    modelo = crear_modelo({"proveedor": "groq", "modelo": "m", "temperatura": 0},
                          cliente=ClienteFalso(_respuesta(tool_calls=[tc])))
    assert "__error__" in modelo.generar([{"role": "user", "content": "x"}]).llamadas[0].argumentos


def test_costo_a_precio_de_lista():
    cfg = {"precio_entrada_usd_mtok": 0.15, "precio_salida_usd_mtok": 0.60}
    assert costo_usd(1_000_000, 1_000_000, cfg) == pytest.approx(0.75)
    assert costo_usd(4000, 300, cfg) == pytest.approx(0.00078)


@pytest.mark.db
def test_bitacora_registra_ejecucion_y_pasos():
    if not os.getenv("DATABASE_URL_ADMIN"):
        pytest.skip("DATABASE_URL_ADMIN no configurada")
    from asistente.bitacora.registro import Ejecucion, Paso, carga_vigente, huella, registrar
    from asistente.db.conexion import conectar_admin
    with conectar_admin() as conn:
        id_carga, corte = carga_vigente(conn)
        e = Ejecucion(usuario="pytest", configuracion="C3", proveedor="groq",
                      modelo_version="openai/gpt-oss-120b", prompt_sha256=huella("instrucciones"),
                      pregunta="¿Cuántas O/S en marzo de 2025?", id_carga=id_carga,
                      fecha_corte_datos=corte, pasos=[Paso(tipo="herramienta", nombre="agregar_ordenes",
                                                           entrada={"desde": "2025-03"},
                                                           resultado={"conteo_ordenes": 1}, ok=True)])
        id_ej = registrar(conn, e)
        fila = conn.execute("SELECT count(*), max(commit_codigo) FROM auditoria.bitacora_paso p "
                            "JOIN auditoria.bitacora b USING (id_ejecucion) WHERE id_ejecucion = %s",
                            (id_ej,)).fetchone()
        assert fila[0] == 1 and fila[1]
        conn.execute("DELETE FROM auditoria.bitacora WHERE id_ejecucion = %s", (id_ej,))
        conn.commit()
