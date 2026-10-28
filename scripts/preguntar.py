"""Hace una pregunta al asistente desde la terminal y la registra en la bitácora.

Uso:  python scripts/preguntar.py "¿Cuál es el saldo de la meta 0006508 al cierre de junio de 2025?"
      python scripts/preguntar.py "..." --config C1        (C1, C2 o C3; por defecto C3)
      python scripts/preguntar.py "..." --ver-pasos         (muestra cada SQL o herramienta usada)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.db.conexion import conectar_admin, conectar_ro  # noqa: E402
from asistente.llm.base import crear_modelo  # noqa: E402
from asistente.orquestador import CONFIGURACIONES, responder  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("pregunta")
    p.add_argument("--config", default="C3", choices=CONFIGURACIONES)
    p.add_argument("--usuario", default="cli")
    p.add_argument("--ver-pasos", action="store_true")
    args = p.parse_args()

    modelo = crear_modelo()
    with conectar_admin() as admin, conectar_ro() as ro:
        r = responder(args.pregunta, args.config, modelo, admin, ro, usuario=args.usuario)

    print("\n" + r.texto + "\n")
    if args.ver_pasos:
        for i, paso in enumerate(r.pasos, start=1):
            print(f"--- paso {i}: {paso.nombre} ({'ok' if paso.ok else 'error'})")
            print("entrada  :", json.dumps(paso.entrada, ensure_ascii=False))
            print("resultado:", json.dumps(paso.resultado, ensure_ascii=False, default=str)[:800])
        print()
    print(f"[{args.config} | {modelo.modelo} | pasos: {len(r.pasos)} | tiempo: {r.tiempo_s:.1f} s | "
          f"tokens: {r.tokens_entrada} entrada / {r.tokens_salida} salida | costo: US$ {r.costo_usd:.6f} | "
          f"abstención: {'sí' if r.abstencion else 'no'}]")
    if r.error:
        print("ERROR:", r.error)
    print(f"Registrado en la bitácora: {r.id_ejecucion}")


if __name__ == "__main__":
    main()
