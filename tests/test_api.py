"""Pruebas del sistema sobre la API (S4): autenticación, control de acceso por perfil (RNF-05),
consulta con un modelo simulado, sustento, evaluación de requerimientos (RNF-04) y panel."""
import os

import pytest

pytestmark = pytest.mark.db
if not (os.getenv("DATABASE_URL_RO") and os.getenv("DATABASE_URL_ADMIN")):
    pytest.skip("Base de datos no configurada", allow_module_level=True)

os.environ.setdefault("API_SECRETO", "x" * 40)

from fastapi.testclient import TestClient  # noqa: E402

from asistente.api import app as api  # noqa: E402
from asistente.api.seguridad import crear_token, hash_clave, leer_token, verificar_clave  # noqa: E402
from asistente.db.conexion import conectar_admin  # noqa: E402
from asistente.llm.base import LlamadaHerramienta, RespuestaLLM  # noqa: E402

USUARIOS = {"pt_jefe": "jefatura", "pt_area": "area_usuaria", "pt_admin": "administrador"}
CLAVE = "clave-de-prueba"


class ModeloFijo:
    proveedor, modelo, temperatura, semilla = "simulado", "fijo", 0, 1

    def __init__(self):
        self.n = 0

    def generar(self, mensajes, herramientas=None):
        self.n += 1
        if self.n % 2 == 1:
            return RespuestaLLM(texto=None, llamadas=[LlamadaHerramienta("t1", "consultar_saldo",
                                {"codigo_finalidad": "0006508", "periodo": "2025-06"})], tokens_entrada=10,
                                tokens_salida=2, mensaje_crudo={"role": "assistant", "content": None, "tool_calls": [
                                    {"id": "t1", "type": "function", "function": {"name": "consultar_saldo", "arguments": "{}"}}]})
        return RespuestaLLM(texto="El saldo es S/ 1 452 526,89.", llamadas=[], tokens_entrada=10, tokens_salida=5,
                            mensaje_crudo={"role": "assistant", "content": "ok"})


@pytest.fixture(scope="module")
def cliente():
    with conectar_admin() as c:
        for u, p in USUARIOS.items():
            c.execute("""INSERT INTO auditoria.usuario (usuario, nombre, perfil, clave_hash) VALUES (%s, %s, %s, %s)
                         ON CONFLICT (usuario) DO UPDATE SET perfil = EXCLUDED.perfil, clave_hash = EXCLUDED.clave_hash""",
                      (u, u, p, hash_clave(CLAVE, 1000)))
        c.commit()
    api.app.dependency_overrides[api.modelo_llm] = ModeloFijo
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    with conectar_admin() as c:
        c.execute("DELETE FROM auditoria.bitacora WHERE usuario = ANY(%s)", (list(USUARIOS),))
        c.execute("DELETE FROM auditoria.usuario WHERE usuario = ANY(%s)", (list(USUARIOS),))
        c.commit()


def _h(cliente, usuario):
    r = cliente.post("/auth/login", json={"usuario": usuario, "clave": CLAVE})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_claves_y_tokens():
    h = hash_clave("secreta", 1000)
    assert verificar_clave("secreta", h) and not verificar_clave("otra", h)
    t = crear_token("a", "jefatura", "s" * 40)
    assert leer_token(t, "s" * 40)["u"] == "a"
    assert leer_token(t, "otro" * 10) is None                          # firma ajena
    assert leer_token(t, "s" * 40, ahora=9e12) is None                 # vencido
    cuerpo, firma = t.split(".")
    assert leer_token(cuerpo[:-2] + "xx." + firma, "s" * 40) is None   # alterado


def test_login_incorrecto_y_sin_token(cliente):
    assert cliente.post("/auth/login", json={"usuario": "pt_jefe", "clave": "mala"}).status_code == 401
    assert cliente.get("/panel/periodos").status_code == 401
    assert cliente.get("/panel/periodos", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_control_de_acceso_por_perfil(cliente):
    area, jefe, admin = (_h(cliente, u) for u in ("pt_area", "pt_jefe", "pt_admin"))
    # panel: jefatura y administrador sí; área usuaria no
    assert cliente.get("/panel/periodos", headers=area).status_code == 403
    assert cliente.get("/panel/periodos", headers=jefe).status_code == 200
    # bitácora completa: solo administrador
    assert cliente.get("/bitacora", headers=jefe).status_code == 403
    assert cliente.get("/bitacora", headers=admin).status_code == 200
    # elegir C1/C2: solo administrador (RF-11)
    assert cliente.post("/consultas", headers=area, json={"pregunta": "¿saldo?", "configuracion": "C1"}).status_code == 403
    assert cliente.post("/consultas", headers=area, json={"pregunta": "¿saldo?", "lote": "x"}).status_code == 403


def test_consulta_y_sustento(cliente):
    area = _h(cliente, "pt_area")
    r = cliente.post("/consultas", headers=area, json={"pregunta": "¿Saldo de la meta 0006508 a junio de 2025?"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["configuracion"] == "C3" and d["pasos"][0]["nombre"] == "consultar_saldo" and not d["abstencion"]
    s = cliente.get(f"/consultas/{d['id_ejecucion']}/sustento", headers=area).json()
    assert s["pasos"][0]["resultado"]["saldo"] == 1452526.89 and s["usuario"] == "pt_area"
    # otro usuario no administrador no ve el sustento ajeno; el administrador sí
    assert cliente.get(f"/consultas/{d['id_ejecucion']}/sustento", headers=_h(cliente, "pt_jefe")).status_code == 403
    assert cliente.get(f"/consultas/{d['id_ejecucion']}/sustento", headers=_h(cliente, "pt_admin")).status_code == 200
    assert cliente.get("/consultas/historial", headers=area).json()[0]["id_ejecucion"] == d["id_ejecucion"]


def test_evaluar_requerimiento_rapido(cliente):
    r = cliente.post("/requerimientos/evaluar", headers=_h(cliente, "pt_area"),
                     json={"codigo_finalidad": "0006508", "monto": 50000, "periodo": "2025-06"}).json()
    assert r["resultado"] == "alcanza" and r["tiempo_s"] <= 3                     # RNF-04
    assert cliente.post("/requerimientos/evaluar", headers=_h(cliente, "pt_area"),
                        json={"codigo_finalidad": "6508", "monto": 1, "periodo": "2025-06"}).status_code == 422


def test_panel(cliente):
    jefe = _h(cliente, "pt_jefe")
    p = cliente.get("/panel/ejecucion", params={"anio": 2025, "mes": 6}, headers=jefe).json()
    assert p["totales"]["pim"] > 0 and len(p["metas"]) > 50
    m = cliente.get("/panel/meta/0006508", params={"anio": 2025}, headers=jefe).json()
    assert [x["mes"] for x in m["meses"]][:2] == [1, 2]
    a = cliente.get("/panel/alertas", params={"periodo": "2025-06", "umbral": 80}, headers=jefe).json()
    assert a["cantidad"] == len(a["metas"])
