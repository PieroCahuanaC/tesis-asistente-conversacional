"""Genera prompts/c2_ejemplos.md: ejemplos pregunta -> SQL de C2 tomados SOLO del conjunto de desarrollo (D20, D28).

Uso:  python scripts/generar_ejemplos_c2.py

Los 12 ejemplos cubren los siete tipos de consulta. Las 18 preguntas de desarrollo restantes no se
muestran a C2, de modo que la prueba piloto de C2 se puede leer también sobre preguntas no vistas.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import load_workbook  # noqa: E402

from asistente.config import RAIZ  # noqa: E402

EJEMPLOS = ["P004", "P010", "P016", "P019", "P027", "P037", "P042", "P044", "P192", "P209", "P056", "P220"]
MOTIVO_T7 = {
    "P056": "2022 está fuera del periodo de los datos (enero 2023 a diciembre 2025).",
    "P220": "entre agosto de 2024 y marzo de 2025 las órdenes no traen código de finalidad, así que no se puede saber a qué meta pertenecen.",
}


def main() -> int:
    ws = load_workbook(RAIZ / "eval" / "banco" / "banco_preguntas.xlsx", read_only=True)["Banco"]
    filas = list(ws.iter_rows(values_only=True))
    banco = {f[0]: dict(zip(filas[0], f)) for f in filas[1:] if f[0]}
    partes = ["Ejemplos resueltos (preguntas de práctica, distintas de las que te harán):", ""]
    for i, pid in enumerate(EJEMPLOS, start=1):
        d = banco[pid]
        if d["Conjunto"] != "desarrollo":
            raise SystemExit(f"{pid} no es del conjunto de desarrollo: no puede ser ejemplo de C2")
        partes.append(f"Ejemplo {i}. Pregunta: {d['Pregunta']}")
        if d["Tipo"] == "T7":
            partes.append(f"No se consulta la base: se responde «[ABSTENCIÓN]» porque {MOTIVO_T7[pid]}")
        else:
            sql = d["SQL_A"].replace("-- paso 1: ", "-- Paso 1, buscar el código de la meta por su nombre: ")
            sql = sql.replace("-- paso 2:", "-- Paso 2, consulta principal con el código encontrado:")
            partes += ["```sql", sql, "```"]
        partes.append("")
    (RAIZ / "prompts" / "c2_ejemplos.md").write_text("\n".join(partes), encoding="utf-8")
    print(f"prompts/c2_ejemplos.md: {len(EJEMPLOS)} ejemplos del conjunto de desarrollo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
