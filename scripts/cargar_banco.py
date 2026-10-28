"""Carga el banco de preguntas (Excel) en eval.pregunta, invisible para el rol del asistente (D8).

Uso:  python scripts/cargar_banco.py        (CIERRE el Excel antes)

Solo se cargan preguntas cuyo doble cálculo coincide (Coinciden = SÍ). Valor_referencia se guarda como
JSON (filas) o como el texto "NO RESPONDIBLE". Si un lote ya usó el banco y las preguntas o referencias
cambian, ejecutar_lote.py lo detecta por la huella y no mezcla resultados.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import load_workbook  # noqa: E402

from asistente.config import RAIZ  # noqa: E402
from asistente.db.conexion import conectar_admin  # noqa: E402
from asistente.evaluacion.comparar import NO_RESPONDIBLE  # noqa: E402
from asistente.evaluacion.familias import INTERPRETACION  # noqa: E402
from asistente.evaluacion.lotes import huella_banco, preguntas  # noqa: E402


def main() -> int:
    ws = load_workbook(RAIZ / "eval" / "banco" / "banco_preguntas.xlsx", read_only=True)["Banco"]
    filas = list(ws.iter_rows(values_only=True))
    cab = filas[0]
    registros, faltan = [], []
    for f in filas[1:]:
        d = dict(zip(cab, f))
        if not d.get("ID"):
            continue
        if d.get("Coinciden") != "SÍ" or d.get("Valor_referencia") in (None, ""):
            faltan.append(d["ID"])
            continue
        ref = d["Valor_referencia"]
        ref_json = json.dumps(NO_RESPONDIBLE) if ref == NO_RESPONDIBLE else json.dumps(json.loads(ref))
        registros.append((d["ID"], d["Conjunto"], d["Tipo"], d["Dificultad"], d["Pregunta"], d["SQL_A"],
                          d["Calculo_B"], ref_json, d["Criterio"], d["Familia"], INTERPRETACION.get(d["Familia"])))
    if faltan:
        print(f"ERROR: {len(faltan)} preguntas sin referencia conciliada: {', '.join(faltan[:10])}. "
              "Ejecute antes scripts/calcular_referencias.py")
        return 1
    with conectar_admin() as c, c.transaction():
        c.cursor().executemany(
            """INSERT INTO eval.pregunta (id_pregunta, conjunto, tipo_consulta, dificultad, texto, sql_referencia_1,
                   sql_referencia_2, valor_referencia, criterio, familia, interpretacion)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
               ON CONFLICT (id_pregunta) DO UPDATE SET conjunto = EXCLUDED.conjunto, tipo_consulta = EXCLUDED.tipo_consulta,
                   dificultad = EXCLUDED.dificultad, texto = EXCLUDED.texto, sql_referencia_1 = EXCLUDED.sql_referencia_1,
                   sql_referencia_2 = EXCLUDED.sql_referencia_2, valor_referencia = EXCLUDED.valor_referencia,
                   criterio = EXCLUDED.criterio, familia = EXCLUDED.familia, interpretacion = EXCLUDED.interpretacion""",
            registros)
        for conjunto in ("desarrollo", "prueba"):
            h = huella_banco(preguntas(c, conjunto))
            c.execute("UPDATE eval.pregunta SET sha256_congelado = %s WHERE conjunto = %s", (h, conjunto))
            print(f"{conjunto}: {len(preguntas(c, conjunto))} preguntas · huella {h[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
