"""Calificación automática de las respuestas del asistente (sección 3.5.3, etapa 4 de 3.5.4).

Una respuesta es CORRECTA si:
  - T7 (criterio abstención): el asistente se abstiene (empieza con «[ABSTENCIÓN]»).
  - Resto: no se abstiene y en su texto aparecen los valores que pide la pregunta:
      montos  -> diferencia <= S/ 1 o <= 0,5 % de la referencia;
      conteos, meses, años, números de orden -> exactos;
      porcentajes -> diferencia <= 0,05 puntos o <= 0,5 %;
      códigos de finalidad (listas) -> el mismo conjunto de códigos, sin importar el orden;
      textos (alcanza / no alcanza, sí / no, O/C / O/S, la meta mayor) -> se reconocen en la respuesta.
Qué columnas de la referencia se exigen depende de la familia de la pregunta (REQUERIDAS).

Cifras no sustentadas (Tabla 22): cifras de la respuesta que no salen de ningún resultado de SQL o de
herramienta de esa ejecución (ni de los datos de la pregunta), ni de una suma, resta o porcentaje
entre dos de ellos. Se excluyen fechas, años, meses y números que ya traía la pregunta.

La calificación automática es el primer paso: el 20 % de las respuestas se revisa a mano (kappa).
"""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from dataclasses import dataclass

from asistente.evaluacion.calculo_a import COLUMNAS
from asistente.orquestador import MARCA_ABSTENCION

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre",
         "noviembre", "diciembre"]
ORDINAL_TRIM = {1: ["primer", "1er", "i ", "t1", "enero"], 2: ["segundo", "2do", "ii ", "t2", "abril"],
                3: ["tercer", "3er", "iii ", "t3", "julio"], 4: ["cuarto", "4to", "iv ", "t4", "octubre"]}
ENTEROS = {"conteo", "mes", "anio", "numero", "trimestre"}
PORCENTAJES = {"porcentaje"}
TEXTOS = {"resultado", "supera", "tipo", "finalidad"}

# Columnas que debe contener una respuesta correcta, por familia (si no figura: todas las de COLUMNAS).
REQUERIDAS = {
    "alcanza": ["saldo", "resultado"],             # la diferencia es saldo − monto: se acepta si falta
    "avance_meta": ["porcentaje", "supera"],
    "comp_conteo_anios": ["anio", "diferencia"],
    "comp_tipo_monto": ["tipo", "diferencia"],
    "comp_metas": ["finalidad", "diferencia"],
    "max_orden": ["numero", "monto"],
}
LISTAS = {"top_dev", "top_dev_periodo", "top_pim", "top_saldo", "top_ordenes", "bottom_avance",
          "listar_avance_mayor", "listar_avance_menor"}


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace(" ", " ").replace(" ", " ")


# ------------------------------------------------------------------ extracción de cifras

_FECHAS = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_NUM = re.compile(r"(?<![\w/])-?\d{1,3}(?:[ .,]\d{3})+(?:[.,]\d{1,2})?(?!\d)|(?<![\w/])-?\d+(?:[.,]\d+)?(?!\d)")


def _interpretaciones(token: str) -> set[float]:
    neg = token.startswith("-")
    t = token.lstrip("-")
    cands: set[str] = set()
    if " " in t:
        partes = t.split(" ")
        cands.add("".join(partes).replace(",", ".") if partes[-1].count(",") == 1 else "".join(partes))
        cands.update(p for p in partes)
    seps = [c for c in t if c in ".,"]
    if not seps:
        cands.add(t.replace(" ", ""))
    elif len(set(seps)) == 2:                    # 1.452.526,89 o 1,452,526.89: el último es el decimal
        dec = seps[-1]
        mil = "," if dec == "." else "."
        cands.add(t.replace(" ", "").replace(mil, "").replace(dec, "."))
    else:
        s = seps[0]
        bloques = t.replace(" ", "").split(s)
        if len(bloques) > 2:                     # 1.452.526 -> miles
            cands.add("".join(bloques))
        elif len(bloques[1]) == 3:               # 41.200 o 41,200: ambiguo
            cands.add("".join(bloques))
            cands.add(bloques[0] + "." + bloques[1])
        else:                                    # 75,43 o 75.43
            cands.add(bloques[0] + "." + bloques[1])
    vals = set()
    for c in cands:
        try:
            v = float(c)
            vals.add(-v if neg else v)
        except ValueError:
            pass
    return vals


def cifras(texto: str) -> list[set[float]]:
    """Cada cifra del texto como el conjunto de valores que puede significar."""
    limpio = _FECHAS.sub(" ", normalizar(texto)).replace("−", "-").replace("–", "-")
    return [v for v in (_interpretaciones(m.group(0)) for m in _NUM.finditer(limpio)) if v]


def _plano(cifras_: list[set[float]]) -> set[float]:
    return set().union(*cifras_) if cifras_ else set()


def _coincide(ref: float, valores: set[float], clase: str) -> bool:
    for v in valores:
        for x in (v, abs(v)) if ref >= 0 else (v, -abs(v)):
            if clase == "entero" and x == ref:
                return True
            if clase == "pct" and abs(x - ref) <= max(0.05, 0.005 * abs(ref)):
                return True
            if clase == "monto" and abs(x - ref) <= max(1.0, 0.005 * abs(ref)):
                return True
    return False


# ------------------------------------------------------------------ valores de texto

def _contiene_texto(col: str, ref, texto_n: str, familia: str) -> bool:
    r = normalizar(str(ref))
    if col == "resultado":
        negativo = bool(re.search(r"\bno (le )?alcanza|\binsuficiente|\bfaltar[ií]a|\bfaltan\b|\bno es suficiente", texto_n))
        return negativo if r == "no alcanza" else (not negativo and bool(re.search(r"\balcanza|\bsuficiente|\bsobrar", texto_n)))
    if col == "supera":
        negativo = bool(re.search(r"\bno (lo )?supera|\bno (lo )?sobrepasa|\bno alcanza|\bpor debajo|\bno excede|\binferior", texto_n))
        return negativo if r == "no" else not negativo
    if col == "tipo":
        clave = {"o/c": r"o/c|compra", "o/s": r"o/s|servicio"}[r]
        otra = {"o/c": r"o/s|servicio", "o/s": r"o/c|compra"}[r]
        m1, m2 = re.search(clave, texto_n), re.search(otra, texto_n)
        return bool(m1) and (not m2 or m1.start() <= m2.start())
    if col == "finalidad":
        codigos = re.findall(r"\b\d{7}\b", texto_n)
        return bool(codigos) and codigos[0] == r
    return r in texto_n


def _contiene_mes(mes: int, texto_n: str) -> bool:
    return MESES[int(mes) - 1] in texto_n or ("septiembre" in texto_n and int(mes) == 9)


def _contiene_trimestre(t: int, texto_n: str) -> bool:
    return any(k in texto_n + " " for k in ORDINAL_TRIM[int(t)]) or bool(re.search(rf"trimestre {int(t)}\b", texto_n))


# ------------------------------------------------------------------ calificación

@dataclass
class Resultado:
    correcta: bool
    abstencion: bool
    cifras_no_sustentadas: int
    con_cifras: bool
    observacion: str


def _sustentadas(numeros: list[set[float]], soportes: set[float]) -> int:
    """Cuenta cifras sin respaldo en los resultados (ni suma, resta o porcentaje de dos de ellos)."""
    base = {round(x, 2) for x in soportes if abs(x) < 1e13}
    if len(base) > 300:                                   # resultados grandes: solo valores directos
        derivados = set()
    else:
        derivados = set()
        for a, b in itertools.combinations(base, 2):
            derivados.update((a + b, a - b, b - a))
            if b:
                derivados.add(100 * a / b)
            if a:
                derivados.add(100 * b / a)
    todos = base | derivados
    faltan = 0
    for vals in numeros:
        if not any(_coincide(v, todos, "monto") or _coincide(v, todos, "pct") for v in vals):
            faltan += 1
    return faltan


def _numeros_de(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for vals in cifras(obj):
            out |= vals
        try:
            out.add(float(obj))
        except ValueError:
            pass
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _numeros_de(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numeros_de(v)
    return out


def calificar(respuesta: str, pregunta: str, familia: str, criterio: str, referencia,
              resultados_pasos: list) -> Resultado:
    texto = respuesta or ""
    abst = texto.strip().startswith(MARCA_ABSTENCION)
    texto_n = normalizar(texto)

    # cifras de la respuesta, sin las que ya venían en la pregunta, años, meses ni números de 1 a 12 sueltos
    de_pregunta = _plano(cifras(pregunta))
    nums = [v for v in cifras(texto)
            if not (v & de_pregunta) and not any(2020 <= x <= 2030 and x == int(x) for x in v)
            and not all(abs(x) <= 12 and x == int(x) for x in v)]
    soportes = _numeros_de(resultados_pasos) | de_pregunta
    no_sust = _sustentadas(nums, soportes) if not abst else len(nums)

    if criterio == "abstencion":
        return Resultado(abst, abst, no_sust, bool(nums), "se abstuvo" if abst else "respondió en vez de abstenerse")
    if abst:
        return Resultado(False, True, no_sust, bool(nums), "se abstuvo en una pregunta respondible")

    filas = referencia
    todas = _plano(cifras(texto))
    if familia in LISTAS:
        esperados = {normalizar(str(f[0])) for f in filas}
        dados = set(re.findall(r"\b\d{7}\b", texto_n))
        ok = dados == esperados
        return Resultado(ok, False, no_sust, bool(nums),
                         "lista correcta" if ok else f"lista: faltan {sorted(esperados - dados)} sobran {sorted(dados - esperados)}")

    cols = COLUMNAS[familia]
    exigidas = REQUERIDAS.get(familia, cols)
    fallas = []
    for col, ref in zip(cols, filas[0]):
        if col not in exigidas:
            continue
        if col in TEXTOS:
            ok = _contiene_texto(col, ref, texto_n, familia)
        elif col == "mes":
            ok = _contiene_mes(ref, texto_n) or _coincide(float(ref), todas, "entero")
        elif col == "trimestre":
            ok = _contiene_trimestre(ref, texto_n)
        elif col in ENTEROS:
            ok = _coincide(float(ref), todas, "entero")
        elif col in PORCENTAJES:
            ok = _coincide(float(ref), todas, "pct")
        else:
            ok = _coincide(float(ref), todas, "monto")
        if not ok and col not in TEXTOS and float(ref) == 0:
            ok = bool(re.search(r"\bno (se )?(registr|hubo|devengo|certifico|comprometio|tuvo)|\bcero\b|\bningun", texto_n))
        if not ok:
            fallas.append(f"{col}={ref}")
    return Resultado(not fallas, False, no_sust, bool(nums), "correcta" if not fallas else "no coincide: " + ", ".join(fallas))


def referencia_de(valor_jsonb) -> object:
    return json.loads(valor_jsonb) if isinstance(valor_jsonb, str) else valor_jsonb
