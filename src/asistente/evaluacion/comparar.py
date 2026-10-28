"""Comparación de resultados con el criterio de corrección de la tesis (sección 3.5.3).

- Numérico: coincide si la diferencia es <= S/ 1 o <= 0,5 % del valor de referencia.
- Lista: mismos elementos, sin importar el orden.
- Abstención: ambos lados «NO RESPONDIBLE».
Se usa para conciliar las dos respuestas de referencia y, más adelante, para calificar al asistente.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

NO_RESPONDIBLE = "NO RESPONDIBLE"
TOLERANCIA_ABS = 1.0
TOLERANCIA_REL = 0.005


def _numero(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    try:
        return float(Decimal(str(v).replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return None


def valores_iguales(a, b) -> bool:
    na, nb = _numero(a), _numero(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= max(TOLERANCIA_ABS, TOLERANCIA_REL * abs(nb))
    if a is None or b is None:
        return a is None and b is None
    return str(a).strip().casefold() == str(b).strip().casefold()


def filas_iguales(f1: list, f2: list) -> bool:
    return len(f1) == len(f2) and all(valores_iguales(x, y) for x, y in zip(f1, f2))


def resultados_equivalentes(r1: list[list], r2: list[list], criterio: str = "numerico") -> bool:
    """Compara dos resultados tabulares (lista de filas). En 'lista' no importa el orden de las filas."""
    if len(r1) != len(r2):
        return False
    if criterio != "lista":
        return all(filas_iguales(a, b) for a, b in zip(r1, r2))
    pendientes = list(r2)
    for fila in r1:
        for i, otra in enumerate(pendientes):
            if filas_iguales(fila, otra):
                pendientes.pop(i)
                break
        else:
            return False
    return True
