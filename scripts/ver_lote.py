"""Muestra las respuestas de un lote (para revisar el ensayo o el piloto).

Uso:  python scripts/ver_lote.py --lote ensayo
      python scripts/ver_lote.py --lote piloto --resumen      (solo totales por configuración)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.db.conexion import conectar_admin  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", required=True)
    ap.add_argument("--resumen", action="store_true")
    a = ap.parse_args()
    with conectar_admin() as c:
        if not a.resumen:
            filas = c.execute(
                """SELECT b.id_pregunta, b.configuracion, b.repeticion, p.valor_referencia::text, b.respuesta, b.error,
                          (SELECT string_agg(coalesce(s.nombre, '') || ': ' || s.entrada::text, E'\\n      ' ORDER BY s.orden)
                             FROM auditoria.bitacora_paso s WHERE s.id_ejecucion = b.id_ejecucion)
                   FROM auditoria.bitacora b JOIN eval.pregunta p USING (id_pregunta)
                   WHERE b.lote = %s ORDER BY b.fecha_hora""", (a.lote,)).fetchall()
            for pid, conf, rep, ref, resp, err, pasos in filas:
                print(f"=== {pid} {conf} r{rep}   referencia: {ref}")
                print(f"    pasos:\n      {pasos or '(ninguno)'}")
                print(f"    respuesta: {resp}")
                if err:
                    print(f"    error: {err}")
        print("\nconfig  ejecuciones  abstenciones  errores  tokens_prom  tiempo_med_s  costo_total_usd")
        for f in c.execute(
                """SELECT configuracion, count(*), count(*) FILTER (WHERE abstencion), count(*) FILTER (WHERE error IS NOT NULL),
                          round(avg(tokens_entrada + tokens_salida)), round(percentile_cont(0.5) WITHIN GROUP (ORDER BY tiempo_s)::numeric, 1),
                          round(sum(costo_usd), 4)
                   FROM auditoria.bitacora WHERE lote = %s GROUP BY 1 ORDER BY 1""", (a.lote,)).fetchall():
            print("  ".join(str(x) for x in f))


if __name__ == "__main__":
    main()
