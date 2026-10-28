"""Adaptador para APIs compatibles con OpenAI Chat Completions (Groq, OpenAI)."""
from __future__ import annotations

import json
import time

from asistente.llm.base import LlamadaHerramienta, RespuestaLLM


class ModeloOpenAICompatible:
    def __init__(self, proveedor: str, modelo: str, temperatura: float, semilla: int | None,
                 esfuerzo_razonamiento: str | None, max_tokens_salida: int,
                 url_base: str | None, clave: str | None, cliente=None, timeout_s: float = 30,
                 max_reintentos: int = 5):
        self.proveedor = proveedor
        self.modelo = modelo
        self.temperatura = temperatura
        self.semilla = semilla
        self.esfuerzo_razonamiento = esfuerzo_razonamiento
        self.max_tokens_salida = max_tokens_salida
        self.max_reintentos = max_reintentos
        if cliente is None:
            from openai import OpenAI
            # Los reintentos se hacen aquí (no en el SDK) para registrar cuántos hubo y cuánto tiempo costaron.
            cliente = OpenAI(api_key=clave, base_url=url_base, max_retries=0, timeout=timeout_s)
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

    def _crear(self, parametros: dict):
        """Llama al proveedor; ante límite de solicitudes, demora o error temporal, espera y reintenta."""
        import openai
        transitorios = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
                        openai.InternalServerError)
        reintentos, perdido = 0, 0.0
        while True:
            inicio = time.perf_counter()
            try:
                r = self._cliente.chat.completions.create(**parametros)
                return r, time.perf_counter() - inicio, reintentos, perdido
            except transitorios as e:
                perdido += time.perf_counter() - inicio
                if reintentos >= self.max_reintentos:
                    raise
                espera = _espera_sugerida(e, reintentos)
                time.sleep(espera)
                perdido += espera
                reintentos += 1

    def generar(self, mensajes: list[dict], herramientas: list[dict] | None = None) -> RespuestaLLM:
        r, tiempo, reintentos, perdido = self._crear(self._parametros(mensajes, herramientas))
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
            reintentos=reintentos,
            tiempo_perdido_s=perdido,
        )


def _espera_sugerida(error, intento: int) -> float:
    """retry-after del proveedor si lo envía (máx. 60 s); si no, 2, 4, 8, 16, 20 s."""
    try:
        valor = float(error.response.headers.get("retry-after"))
        return min(max(valor, 0.5), 60.0)
    except Exception:
        return float(min(2 ** (intento + 1), 20))
