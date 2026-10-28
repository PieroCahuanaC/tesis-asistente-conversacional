"""Califica automáticamente las respuestas de un lote (etapa 4 de 3.5.4) y muestra la exactitud.

Uso:  python scripts/calificar_lote.py --lote piloto
      python scripts/calificar_lote.py --lote principal --detalle      (lista cada respuesta incorrecta)

Escribe en eval.calificacion (calificador = 'automatico'; se reemplaza si se vuelve a calificar) y
exporta reports/lotes/<lote>/calificacion_automatica.csv.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.config import RAIZ  # noqa: E402
from asistente.db.conexion import conectar_admin  # noqa: E402
from asistente.evaluacion.calificar import _plano_texto, calificar, referencia_de  # noqa: E402
from asistente.orquestador import ERROR_MAX_PASOS  # noqa: E402

CONSULTA = """
SELECT DISTINCT ON (b.id_pregunta, b.configuracion, b.repeticion)
       b.id_ejecucion, b.id_pregunta, b.configuracion, b.repeticion, b.respuesta, b.tiempo_s,
       b.tokens_entrada, b.tokens_salida, b.costo_usd, p.texto, p.familia, p.criterio, p.tipo_consulta,
       p.dificultad, p.valor_referencia,
       coalesce((SELECT json_agg(s.resultado ORDER BY s.orden) FROM auditoria.bitacora_paso s
                  WHERE s.id_ejecucion = b.id_ejecucion), '[]'::json)
FROM auditoria.bitacora b JOIN eval.pregunta p USING (id_pregunta)
WHERE b.lote = %s AND (b.error IS NULL OR b.error LIKE %s)
ORDER BY b.id_pregunta, b.configuracion, b.repeticion, b.fecha_hora DESC
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", required=True)
    ap.add_argument("--detalle", action="store_true")
    a = ap.parse_args()
    with conectar_admin() as c:
        filas = c.execute(CONSULTA, (a.lote, ERROR_MAX_PASOS + "%")).fetchall()
        if not filas:
            raise SystemExit(f"El lote «{a.lote}» no tiene ejecuciones válidas.")
        nombres: dict[str, set[str]] = {}
        for cod, nombre in c.execute("SELECT DISTINCT finalidad, nombre_meta FROM datos.ejecucion_presupuestal "
                                     "WHERE nombre_meta IS NOT NULL").fetchall():
            nombres.setdefault(cod, set()).add(_plano_texto(nombre))
        salida = []
        for (id_ej, pid, conf, rep, resp, t, ti, to, costo, texto, fam, crit, tipo, dif, ref, pasos) in filas:
            r = calificar(resp or "", texto, fam, crit, referencia_de(ref), pasos, nombres)
            salida.append(dict(id_ejecucion=str(id_ej), id_pregunta=pid, configuracion=conf, repeticion=rep, tipo=tipo,
                               dificultad=dif, familia=fam, correcta=r.correcta, abstencion=r.abstencion,
                               con_cifras=r.con_cifras, cifras_no_sustentadas=r.cifras_no_sustentadas,
                               observacion=r.observacion, tiempo_s=float(t or 0), tokens=(ti or 0) + (to or 0),
                               costo_usd=float(costo or 0), respuesta=resp))
        with c.transaction():
            c.cursor().executemany(
                """INSERT INTO eval.calificacion (id_ejecucion, calificador, correcta, abstencion, cifras_no_sustentadas,
                       con_cifras, observacion) VALUES (%s, 'automatico', %s, %s, %s, %s, %s)
                   ON CONFLICT (id_ejecucion, calificador) DO UPDATE SET correcta = EXCLUDED.correcta,
                       abstencion = EXCLUDED.abstencion, cifras_no_sustentadas = EXCLUDED.cifras_no_sustentadas,
                       con_cifras = EXCLUDED.con_cifras, observacion = EXCLUDED.observacion, fecha = now()""",
                [(s["id_ejecucion"], s["correcta"], s["abstencion"], s["cifras_no_sustentadas"], s["con_cifras"],
                  s["observacion"]) for s in salida])

    carpeta = RAIZ / "reports" / "lotes" / a.lote
    carpeta.mkdir(parents=True, exist_ok=True)
    with open(carpeta / "calificacion_automatica.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(salida[0]))
        w.writeheader()
        w.writerows(sorted(salida, key=lambda s: (s["id_pregunta"], s["configuracion"], s["repeticion"])))

    por = defaultdict(lambda: defaultdict(list))
    for s in salida:
        por[s["configuracion"]]["global"].append(s["correcta"])
        por[s["configuracion"]][s["tipo"]].append(s["correcta"])
    tipos = sorted({s["tipo"] for s in salida})
    print(f"Lote «{a.lote}»: {len(salida)} respuestas calificadas\n")
    print("config  exactitud      " + "  ".join(f"{t:>6}" for t in tipos) + "   cifras_no_sust")
    for conf in sorted(por):
        g = por[conf]["global"]
        con = [s for s in salida if s["configuracion"] == conf and s["con_cifras"] and not s["abstencion"]]
        tasa = sum(1 for s in con if s["cifras_no_sustentadas"] > 0) / len(con) if con else 0
        print(f"{conf:6}  {sum(g):3}/{len(g):<3} {100 * sum(g) / len(g):5.1f} %  "
              + "  ".join(f"{100 * sum(por[conf][t]) / len(por[conf][t]):5.0f}%" for t in tipos) + f"   {100 * tasa:5.1f} %")
    if a.detalle:
        print("\nIncorrectas:")
        for s in salida:
            if not s["correcta"]:
                print(f"  {s['id_pregunta']} {s['configuracion']} r{s['repeticion']}: {s['observacion']}")
                print(f"      {(s['respuesta'] or '')[:300]}")
    print(f"\nDetalle: {carpeta / 'calificacion_automatica.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
