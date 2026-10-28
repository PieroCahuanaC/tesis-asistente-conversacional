"""Adaptador para APIs compatibles con OpenAI Chat Completions (Groq, OpenAI)."""
from __future__ import annotations

import json
import time

from asistente.llm.base import LlamadaHerramienta, RespuestaLLM


class ModeloOpenAICompatible:
    def __init__(self, proveedor: str, modelo: str, temperatura: float, semilla: int | None,
                 esfuerzo_razonamiento: str | None, max_tokens_salida: int,
                 url_base: str | None, clave: str | None, cliente=None):
        self.proveedor = proveedor
        self.modelo = modelo
        self.temperatura = temperatura
        self.semilla = semilla
        self.esfuerzo_razonamiento = esfuerzo_razonamiento
        self.max_tokens_salida = max_tokens_salida
        if cliente is None:
            from openai import OpenAI
            # max_retries reintenta con espera exponencial ante 429 (límites del nivel gratuito).
            cliente = OpenAI(api_key=clave, base_url=url_base, max_retries=6, timeout=60)
        self._cliente = cliente

    def _parametros(self, mensajes: list[dict], herramientas: list[dict] | None) -> dict:
        p = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": self.temperatura,
            "max_completion_tokens": self.max_tokens_salida,
        }
        if self.semilla is not None:
            p["seed"] = self.semilla
        if self.esfuerzo_razonamiento and self.proveedor in ("groq", "cerebras", "deepinfra"):
            p["reasoning_effort"] = self.esfuerzo_razonamiento
        if herramientas:
            p["tools"] = herramientas
            p["tool_choice"] = "auto"
        return p

    def generar(self, mensajes: list[dict], herramientas: list[dict] | None = None) -> RespuestaLLM:
        inicio = time.perf_counter()
        r = self._cliente.chat.completions.create(**self._parametros(mensajes, herramientas))
        tiempo = time.perf_counter() - inicio
        eleccion = r.choices[0]
        msg = eleccion.message

        llamadas = []
        for tc in msg.tool_calls or []:
            crudo = tc.function.arguments or "{}"
            try:
                args = json.loads(crudo)
            except json.JSONDecodeError:
                args = {"__error__": "argumentos no son JSON válido"}
            llamadas.append(LlamadaHerramienta(id=tc.id, nombre=tc.function.name,
                                               argumentos=args, argumentos_crudos=crudo))

        mensaje_crudo = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            mensaje_crudo["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls]

        uso = r.usage
        return RespuestaLLM(
            texto=msg.content,
            llamadas=llamadas,
            tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
            tokens_salida=getattr(uso, "completion_tokens", 0) or 0,
            modelo_reportado=getattr(r, "model", None),
            tiempo_s=tiempo,
            finalizacion=eleccion.finish_reason,
            mensaje_crudo=mensaje_crudo,
        )
