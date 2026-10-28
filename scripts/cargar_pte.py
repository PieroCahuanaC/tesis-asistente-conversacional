"""Etapa 1 (OE1): integra las órdenes del PTE y las carga en PostgreSQL.

Uso:  python scripts/cargar_pte.py [--fecha-corte AAAA-MM-DD] [--sin-bd]

Produce:
  data/interim/ordenes_pte.parquet   (no se versiona: contiene seudónimos)
  data/manifest_pte.csv              (sí se versiona: sha256 de cada archivo de origen)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.config import RAIZ  # noqa: E402
from asistente.ingesta.pte import construir_ordenes  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fecha-corte", help="Fecha de descarga de los archivos del PTE (AAAA-MM-DD)")
    p.add_argument("--sin-bd", action="store_true", help="Solo genera los archivos, no carga PostgreSQL")
    args = p.parse_args()

    r = construir_ordenes()
    (RAIZ / "data" / "interim").mkdir(parents=True, exist_ok=True)
    salida = r.ordenes.copy()
    for c in ("monto_soles", "monto_uit"):
        salida[c] = salida[c].astype(str)
    salida.to_parquet(RAIZ / "data" / "interim" / "ordenes_pte.parquet", index=False)
    r.manifiesto.to_csv(RAIZ / "data" / "manifest_pte.csv", index=False, encoding="utf-8")

    print(r.embudo.to_string(index=False))
    for a in r.advertencias:
        print("ADVERTENCIA:", a)
    regrabados = r.manifiesto[r.manifiesto.regrabado_en_excel]
    if len(regrabados):
        print(f"ADVERTENCIA: {len(regrabados)} archivos fueron guardados de nuevo en Excel "
              f"(no son el original del portal): {', '.join(regrabados.archivo)}")

    if not args.sin_bd:
        from asistente.db.cargar import cargar_ordenes
        from asistente.db.conexion import conectar_admin
        with conectar_admin() as conn:
            id_carga = cargar_ordenes(conn, r.ordenes, r.manifiesto, args.fecha_corte)
        print(f"Carga registrada en datos.carga con id_carga = {id_carga}")


if __name__ == "__main__":
    main()
