"""Autenticación y control de acceso por perfil (RF-18, RNF-05).

- Claves: PBKDF2-SHA256 con sal aleatoria (biblioteca estándar).
- Sesión: token firmado con HMAC-SHA256 (clave API_SECRETO del .env, RNF-06) que caduca en 8 horas.
- Permisos: tabla PERMISOS; cada endpoint declara la función que requiere.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

PERFILES = ("jefatura", "area_usuaria", "administrador")
TODOS = set(PERFILES)
PERMISOS: dict[str, set[str]] = {
    "consultar": TODOS,                                 # CU-01, CU-03: asistente conversacional
    "evaluar_requerimiento": TODOS,                     # CU-02
    "panel": {"jefatura", "administrador"},             # CU-04: ejecución por meta y alertas
    "elegir_configuracion": {"administrador"},          # RF-11: C1 / C2 / C3 por sesión
    "bitacora": {"administrador"},                      # RF-19: revisar todas las ejecuciones
}
DURACION_S = 8 * 3600
ITERACIONES = 240_000


def hash_clave(clave: str, iteraciones: int = ITERACIONES) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), iteraciones).hex()
    return f"pbkdf2_sha256${iteraciones}${sal}${h}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        algoritmo, it, sal, h = guardado.split("$")
    except ValueError:
        return False
    if algoritmo != "pbkdf2_sha256":
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), int(it)).hex()
    return hmac.compare_digest(calculado, h)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _de_b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def crear_token(usuario: str, perfil: str, secreto: str, ahora: float | None = None) -> str:
    carga = {"u": usuario, "p": perfil, "exp": int((ahora or time.time()) + DURACION_S)}
    cuerpo = _b64(json.dumps(carga, separators=(",", ":")).encode())
    firma = _b64(hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).digest())
    return f"{cuerpo}.{firma}"


def leer_token(token: str, secreto: str, ahora: float | None = None) -> dict | None:
    """Devuelve {'u', 'p', 'exp'} si la firma es válida y no caducó; si no, None."""
    try:
        cuerpo, firma = token.split(".")
        esperada = _b64(hmac.new(secreto.encode(), cuerpo.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        carga = json.loads(_de_b64(cuerpo))
    except Exception:
        return None
    if carga.get("exp", 0) < (ahora or time.time()) or carga.get("p") not in PERFILES:
        return None
    return carga


def puede(perfil: str, funcion: str) -> bool:
    return perfil in PERMISOS.get(funcion, set())
