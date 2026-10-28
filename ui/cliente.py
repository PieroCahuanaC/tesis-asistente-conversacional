"""Cliente de la API para la interfaz: la interfaz no toca la base ni el modelo (RNF-09)."""
from __future__ import annotations

import os

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")


class ErrorApi(Exception):
    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado


def llamar(metodo: str, ruta: str, token: str | None = None, timeout: float = 180, **kw):
    cab = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.request(metodo, f"{API_URL}{ruta}", headers=cab, timeout=timeout, **kw)
    except requests.RequestException:
        raise ErrorApi(0, "No se pudo conectar con el servicio del asistente. Verifique que la API esté encendida.") from None
    if r.status_code >= 400:
        try:
            detalle = r.json().get("detail")
        except ValueError:
            detalle = None
        if isinstance(detalle, list):                      # errores de validación de FastAPI
            detalle = "Revise los datos ingresados: " + "; ".join(str(d.get("msg")) for d in detalle)
        raise ErrorApi(r.status_code, detalle or f"Error {r.status_code}")
    return r.json()
