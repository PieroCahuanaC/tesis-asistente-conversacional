"""Etapa 1 (OE1): carga la ejecución presupuestal del MEF y la cruza con las órdenes del PTE.

Uso:  python scripts/cargar_mef.py --fecha-corte AAAA-MM-DD
      (fecha en que se descargaron los CSV de datos abiertos del MEF)

Reemplaza por completo la ejecución cargada antes (los CSV son una foto a la fecha de descarga),
actualiza el catálogo de finalidades (nombre limpio, tipo de gasto, en_mef) y el tipo de gasto
de las órdenes.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.config import commit_actual  # noqa: E402
from asistente.db.conexion import conectar_admin  # noqa: E402
from asistente.ingesta.mef import construir_ejecucion  # noqa: E402

COLUMNAS = ["anio", "mes", "sec_func", "finalidad", "nombre_meta", "tipo_act_proy", "producto_proyecto",
            "producto_proyecto_nombre", "actividad_nombre", "funcion_nombre", "categoria_gasto",
            "fuente_financiamiento", "rubro", "generica_nombre", "clasificador", "clasificador_nombre",
            "pia", "pim", "certificado", "comprometido_anual", "comprometido_mensual", "devengado", "girado"]


def _fecha(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{texto}' no es una fecha válida (AAAA-MM-DD)") from None


def _nativo(v):
    if v is None:
        return None
    return v.item() if hasattr(v, "item") else v


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fecha-corte", type=_fecha, required=True,
                   help="Fecha de descarga de los CSV del MEF (AAAA-MM-DD)")
    args = p.parse_args()

    r = construir_ejecucion()
    for a in r.advertencias:
        print("ADVERTENCIA:", a)

    with conectar_admin() as conn, conn.transaction():
        id_carga = conn.execute(
            "INSERT INTO datos.carga (fuente, fecha_corte, archivos, filas, commit_codigo) "
            "VALUES ('MEF', %s, %s, %s, %s) RETURNING id_carga",
            (args.fecha_corte, json.dumps(r.manifiesto.to_dict("records")), len(r.ejecucion), commit_actual()),
        ).fetchone()[0]
        conn.execute("DELETE FROM datos.ejecucion_presupuestal")
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO datos.ejecucion_presupuestal ({', '.join(COLUMNAS)}, id_carga) "
                f"VALUES ({', '.join(['%s'] * (len(COLUMNAS) + 1))})",
                [[_nativo(v) for v in fila] + [id_carga]
                 for fila in r.ejecucion[COLUMNAS].itertuples(index=False, name=None)],
            )
            cur.executemany(
                "INSERT INTO datos.finalidad (codigo_finalidad, nombre_mef, tipo_gasto, en_mef) "
                "VALUES (%s, %s, %s, TRUE) ON CONFLICT (codigo_finalidad) DO UPDATE SET "
                "nombre_mef = EXCLUDED.nombre_mef, tipo_gasto = EXCLUDED.tipo_gasto, en_mef = TRUE",
                list(r.finalidades.itertuples(index=False, name=None)),
            )
        conn.execute("UPDATE datos.finalidad SET en_mef = FALSE WHERE codigo_finalidad NOT IN "
                     "(SELECT DISTINCT finalidad FROM datos.ejecucion_presupuestal)")
        conn.execute("UPDATE datos.orden o SET tipo_gasto = f.tipo_gasto FROM datos.finalidad f "
                     "WHERE o.codigo_finalidad = f.codigo_finalidad")

        resumen = conn.execute("""
            SELECT anio, count(DISTINCT sec_func) metas, count(DISTINCT finalidad) finalidades,
                   sum(pia) pia, sum(pim) pim, sum(certificado) cert, sum(devengado) dev
            FROM datos.ejecucion_presupuestal GROUP BY anio ORDER BY anio""").fetchall()
        cruce = conn.execute("""
            SELECT count(*) FILTER (WHERE o.con_codigo),
                   count(*) FILTER (WHERE o.con_codigo AND EXISTS (
                       SELECT 1 FROM datos.ejecucion_presupuestal e
                       WHERE e.anio = o.anio AND e.finalidad = o.codigo_finalidad))
            FROM datos.orden o WHERE o.incluida""").fetchone()

    print(f"Carga MEF registrada con id_carga = {id_carga} ({len(r.ejecucion):,} filas)")
    print(f"{'Año':>5} {'Metas':>6} {'Finalid.':>8} {'PIA':>16} {'PIM':>16} {'Certificado':>16} {'Devengado':>16}")
    for anio, metas, fins, pia, pim, cert, dev in resumen:
        print(f"{anio:>5} {metas:>6} {fins:>8} {pia:>16,.2f} {pim:>16,.2f} {cert:>16,.2f} {dev:>16,.2f}")
    if cruce[0]:
        print(f"Órdenes <= 8 UIT con código cuya finalidad existe en el MEF ese año: "
              f"{cruce[1]:,} de {cruce[0]:,} ({100 * cruce[1] / cruce[0]:.2f} %)")


if __name__ == "__main__":
    main()
