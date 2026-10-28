"""Funciones puras de limpieza de las órdenes del PTE (etapa 1 de la subsección 3.5.4).

Cada función es determinista y se prueba en tests/test_limpieza.py.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Código de finalidad de 7 dígitos. Formatos observados en el PTE 2023-2025:
#   "-0000888 GESTION ADMINISTRATIVA"                (ene-2023 a jul-2024)
#   "- 0006508 MANTENIMIENTO DE PARQUES Y JARDINES"  (abr-2025 a dic-2025)
#   "NO SE NOTIFICO, ...-0422086  MANTENIMIENTO ..."  (código a mitad del texto)
# Se exige un guion o el inicio del texto antes del código para no capturar
# números de 7 dígitos que aparezcan en una descripción libre.
_RE_FINALIDAD = re.compile(r"(?:^|-)\s*(\d{7})\b[\s\-:]*(.*)", re.DOTALL)
_RE_MONTO = re.compile(r"^\s*S/\.?\s*([\d.,]+)\s*$")
_RE_ESPACIOS = re.compile(r"\s+")

ESTADOS = {"emitida", "comprometida", "devengada", "anulada"}


def limpiar_texto(valor: object) -> str | None:
    """Recorta y colapsa espacios. Devuelve None para vacíos y para el literal 'NAN'."""
    if valor is None:
        return None
    texto = _RE_ESPACIOS.sub(" ", str(valor)).strip()
    if texto == "" or texto.upper() == "NAN":
        return None
    return texto


def parsear_monto(valor: object) -> Decimal:
    """'S/. 1542.5' -> Decimal('1542.5'). Error si el formato no es el esperado."""
    m = _RE_MONTO.match(str(valor))
    if not m:
        raise ValueError(f"Monto con formato no reconocido: {valor!r}")
    numero = m.group(1).replace(",", "")
    try:
        return Decimal(numero)
    except InvalidOperation as e:
        raise ValueError(f"Monto no numérico: {valor!r}") from e


def parsear_fecha(valor: object) -> date | None:
    """'2023-08-01 00:00:00.0' -> date(2023, 8, 1). Vacío -> None."""
    texto = limpiar_texto(valor)
    if texto is None:
        return None
    return datetime.strptime(texto[:10], "%Y-%m-%d").date()


def extraer_finalidad(descripcion: object) -> tuple[str | None, str | None]:
    """Devuelve (código de 7 dígitos, nombre tal como figura en el PTE) o (None, None)."""
    texto = limpiar_texto(descripcion)
    if texto is None:
        return None, None
    m = _RE_FINALIDAD.search(texto)
    if not m:
        return None, None
    nombre = limpiar_texto(m.group(2))
    return m.group(1), nombre


def normalizar_tipo_orden(valor: object) -> str:
    texto = limpiar_texto(valor)
    if texto not in {"O/C", "O/S"}:
        raise ValueError(f"Tipo de orden no reconocido: {valor!r}")
    return texto


def normalizar_tipo_contratacion(valor: object) -> str | None:
    """Categorías: 'hasta_8_uit', 'deviene_seleccion' o None (campo vacío desde ago-2024)."""
    texto = limpiar_texto(valor)
    if texto is None:
        return None
    if texto.lower().startswith("deviene"):
        return "deviene_seleccion"
    if "8 UIT" in texto.upper():
        return "hasta_8_uit"
    raise ValueError(f"Tipo de contratación no reconocido: {valor!r}")


def normalizar_estado(valor: object) -> str:
    texto = (limpiar_texto(valor) or "").lower()
    if texto not in ESTADOS:
        raise ValueError(f"Estado no reconocido: {valor!r}")
    return texto


def normalizar_ruc(valor: object) -> str:
    """Los RUC llegan como texto; algunos lectores los convierten en float ('20605570870.0')."""
    texto = limpiar_texto(valor) or ""
    if texto.endswith(".0"):
        texto = texto[:-2]
    if not re.fullmatch(r"\d{11}", texto):
        raise ValueError(f"RUC inválido: {valor!r}")
    return texto


def es_persona_natural(ruc: str, prefijos: list[str]) -> bool:
    return ruc[:2] in prefijos


def seudonimizar(ruc: str, clave: str) -> str:
    """Seudónimo estable e irreversible sin la clave: 'PN-' + 12 hex de HMAC-SHA256."""
    if not clave or clave == "CAMBIAR":
        raise RuntimeError("SEUDONIMO_CLAVE no está configurada en .env")
    digest = hmac.new(clave.encode("utf-8"), ruc.encode("utf-8"), hashlib.sha256).hexdigest()
    return "PN-" + digest[:12]


def en_tramo(anio: int, mes: int, desde: str, hasta: str) -> bool:
    """True si (anio, mes) cae en el intervalo cerrado [desde, hasta] con formato 'AAAA-MM'."""
    clave = f"{anio:04d}-{mes:02d}"
    return desde <= clave <= hasta
