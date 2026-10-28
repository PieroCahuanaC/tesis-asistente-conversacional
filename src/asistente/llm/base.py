"""Interfaz independiente del proveedor del LLM (RNF-09).

Formato canónico de mensajes: el de chat de OpenAI (role / content / tool_calls / tool_call_id),
que Groq y OpenAI aceptan tal cual. Un adaptador de otro proveedor traduce desde y hacia él.
Cambiar de proveedor = cambiar config/settings.yaml, sin tocar la lógica del asistente.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from asistente.config import ajustes


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict
    argumentos_crudos: str = ""


@dataclass
class RespuestaLLM:
    texto: str | None
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo_reportado: str | None = None
    tiempo_s: float = 0.0
    finalizacion: str | None = None
    mensaje_crudo: dict | None = None    # mensaje del asistente para reenviarlo en el historial


class ModeloLenguaje(Protocol):
    proveedor: str
    modelo: str
    temperatura: float
    semilla: int | None

    def generar(self, mensajes: list[dict], herramientas: list[dict] | None = None) -> RespuestaLLM: ...


def costo_usd(tokens_entrada: int, tokens_salida: int, cfg: dict | None = None) -> float:
    """Costo a precio de lista (indicador de eficiencia), aunque se use un nivel gratuito."""
    cfg = cfg or ajustes()["llm"]
    return (tokens_entrada * cfg["precio_entrada_usd_mtok"]
            + tokens_salida * cfg["precio_salida_usd_mtok"]) / 1_000_000


_URL_BASE = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": None,  # URL por defecto del SDK
}
_VARIABLE_CLAVE = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY"}


def crear_modelo(cfg: dict | None = None, cliente=None) -> ModeloLenguaje:
    """Fábrica: construye el adaptador indicado en settings.yaml."""
    from asistente.config import env
    from asistente.llm.openai_compat import ModeloOpenAICompatible

    cfg = cfg or ajustes()["llm"]
    proveedor = cfg["proveedor"]
    if proveedor not in _URL_BASE:
        raise ValueError(f"Proveedor no soportado todavía: {proveedor}")
    return ModeloOpenAICompatible(
        proveedor=proveedor,
        modelo=cfg["modelo"],
        temperatura=cfg["temperatura"],
        semilla=cfg.get("semilla"),
        esfuerzo_razonamiento=cfg.get("esfuerzo_razonamiento"),
        max_tokens_salida=cfg.get("max_tokens_salida", 1024),
        url_base=_URL_BASE[proveedor],
        clave=None if cliente else env(_VARIABLE_CLAVE[proveedor]),
        cliente=cliente,
    )
