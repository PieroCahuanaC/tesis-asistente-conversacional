"""Filtra los CSV nacionales de gasto del MEF (datos abiertos) a las filas de Uchumayo.

Uso:  python scripts/filtrar_mef.py
      python scripts/filtrar_mef.py ruta\\a\\2023-Gasto.csv ruta\\a\\2024-Gasto.csv ...

Sin argumentos procesa todos los .csv de data/raw/mef/ (excepto los ya filtrados).
Por cada archivo, en una sola lectura:
  - copia la cabecera y las filas que contienen «UCHUMAYO» en data/raw/mef/filtrado/
  - calcula el sha256 del archivo original (huella de la fuente para la tesis)
y escribe data/manifest_mef.csv (sí se versiona).

Lee en binario, línea por línea: no carga los GB en memoria y no depende de la codificación.
El filtro es amplio a propósito (puede traer proyectos de otras entidades ubicados en
Uchumayo); la selección exacta por unidad ejecutora se hace después, en la ingesta.
"""
from __future__ import annotations

import csv
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DIR_MEF = RAIZ / "data" / "raw" / "mef"
DIR_SALIDA = DIR_MEF / "filtrado"
PATRON = b"UCHUMAYO"


def filtrar(origen: Path) -> dict:
    destino = DIR_SALIDA / f"{origen.stem}_UCHUMAYO.csv"
    h = hashlib.sha256()
    leidas = guardadas = 0
    inicio = time.time()
    with open(origen, "rb") as f, open(destino, "wb") as out:
        cabecera = f.readline()
        h.update(cabecera)
        out.write(cabecera)
        for linea in f:
            h.update(linea)
            leidas += 1
            if PATRON in linea.upper():
                out.write(linea)
                guardadas += 1
            if leidas % 2_000_000 == 0:
                print(f"  {origen.name}: {leidas:,} filas leídas...", flush=True)
    print(f"{origen.name}: {leidas:,} filas leídas, {guardadas:,} guardadas -> {destino.name} "
          f"({time.time() - inicio:.0f} s)")
    if guardadas == 0:
        print(f"  ATENCIÓN: ninguna fila contiene UCHUMAYO en {origen.name}")
    return {"archivo": origen.name, "bytes": origen.stat().st_size, "sha256": h.hexdigest(),
            "filas": leidas, "filas_uchumayo": guardadas, "archivo_filtrado": destino.name,
            "fecha_modificacion": datetime.fromtimestamp(origen.stat().st_mtime).isoformat(timespec="seconds"),
            "cabecera": cabecera.decode("utf-8", errors="replace").strip()}


def main() -> None:
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    archivos = [Path(a) for a in sys.argv[1:]] or sorted(DIR_MEF.glob("*.csv"))
    if not archivos:
        sys.exit(f"No hay archivos .csv en {DIR_MEF}. Copie ahí los CSV del MEF o páselos como argumento.")
    filas = [filtrar(a) for a in archivos]
    manifiesto = RAIZ / "data" / "manifest_mef.csv"
    with open(manifiesto, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"Manifiesto escrito en {manifiesto.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
