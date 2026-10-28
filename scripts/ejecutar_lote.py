"""Ejecución por lotes del banco de preguntas en C1, C2 y C3 (etapas 3 y 5 de 3.5.4; RF-20).

Uso:
  python scripts/ejecutar_lote.py --lote piloto --conjunto desarrollo          (prueba piloto, 4.5.3)
  python scripts/ejecutar_lote.py --lote principal --conjunto prueba           (600 ejecuciones)
  python scripts/ejecutar_lote.py --lote estabilidad --conjunto prueba --config C3 --repeticiones 3 --muestra 0.2
Opciones:
  --config C1 C2 C3     configuraciones (por defecto las tres)
  --pausa 10            segundos de espera entre ejecuciones (útil en el nivel gratuito de Groq)
  --max 5               ejecuta como máximo N tareas y se detiene (para probar)
  --ids P001 P002       solo esas preguntas

Se puede cortar (Ctrl+C) y volver a ejecutar el mismo comando: continúa donde quedó.
Cada ejecución queda en auditoria.bitacora con su lote, pregunta, configuración y repetición.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.config import ajustes, commit_actual  # noqa: E402
from asistente.db.conexion import conectar_admin, conectar_ro  # noqa: E402
from asistente.evaluacion.lotes import (completadas, es_falla_proveedor, huella_banco,  # noqa: E402
                                        muestra_estratificada, planificar, preguntas)
from asistente.llm.base import crear_modelo  # noqa: E402
from asistente.orquestador import CONFIGURACIONES, responder  # noqa: E402

MAX_FALLAS_SEGUIDAS = 3


def registrar_lote(admin, args, filas, modelo) -> None:
    h = huella_banco(filas)
    previo = admin.execute("SELECT banco_sha256, modelo, proveedor FROM eval.lote WHERE nombre = %s",
                           (args.lote,)).fetchone()
    if previo is None:
        admin.execute(
            """INSERT INTO eval.lote (nombre, descripcion, conjunto, configuraciones, repeticiones, banco_sha256,
                   modelo, proveedor, semilla, commit_inicio) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (args.lote, args.descripcion, args.conjunto, args.config, args.repeticiones, h, modelo.modelo,
             modelo.proveedor, modelo.semilla, commit_actual()))
        admin.commit()
        return
    if previo[0] != h or previo[1] != modelo.modelo or previo[2] != modelo.proveedor:
        raise SystemExit(f"El lote «{args.lote}» se inició con otro banco, modelo o proveedor ({previo[2]}/{previo[1]}). "
                         "Use otro nombre de lote para no mezclar resultados.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", required=True)
    ap.add_argument("--conjunto", required=True, choices=["desarrollo", "prueba"])
    ap.add_argument("--config", nargs="+", default=list(CONFIGURACIONES), choices=CONFIGURACIONES)
    ap.add_argument("--repeticiones", type=int, default=1)
    ap.add_argument("--muestra", type=float, help="fracción estratificada por tipo (p. ej. 0.2)")
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--pausa", type=float, default=0.0)
    ap.add_argument("--max", type=int)
    ap.add_argument("--descripcion")
    args = ap.parse_args()

    semilla = int(ajustes()["llm"]["semilla"])
    modelo = crear_modelo()
    with conectar_admin() as admin, conectar_ro() as ro:
        filas = preguntas(admin, args.conjunto, args.ids)
        if not filas:
            raise SystemExit("No hay preguntas cargadas: ejecute primero python scripts/cargar_banco.py")
        if args.muestra:
            filas = muestra_estratificada(filas, args.muestra, semilla)
        registrar_lote(admin, args, filas, modelo)
        tareas = planificar(filas, args.config, args.repeticiones, semilla)
        hechas = completadas(admin, args.lote)
        pendientes = [t for t in tareas if (t.id_pregunta, t.configuracion, t.repeticion) not in hechas]
        print(f"Lote «{args.lote}»: {len(tareas)} tareas · {len(tareas) - len(pendientes)} ya hechas · "
              f"{len(pendientes)} pendientes · modelo {modelo.modelo}")

        fallas_seguidas = tok = 0
        costo = 0.0
        hechas_ahora = 0
        try:
            for n, t in enumerate(pendientes, start=1):
                if args.max and hechas_ahora >= args.max:
                    break
                r = responder(t.texto, t.configuracion, modelo, admin, ro, usuario=f"lote:{args.lote}",
                              id_pregunta=t.id_pregunta, repeticion=t.repeticion, lote=args.lote)
                if es_falla_proveedor(r.error):
                    fallas_seguidas += 1
                    print(f"[{n}/{len(pendientes)}] {t.id_pregunta} {t.configuracion} r{t.repeticion}  FALLA DEL PROVEEDOR "
                          f"(se reintentará): {r.error[:160]}")
                    if fallas_seguidas >= MAX_FALLAS_SEGUIDAS:
                        print("\nTres fallas seguidas del proveedor: probablemente se agotó el límite de tokens del día "
                              "o no hay conexión. Vuelva a ejecutar el mismo comando más tarde; continuará donde quedó.")
                        break
                    time.sleep(max(args.pausa, 20))
                    continue
                fallas_seguidas = 0
                hechas_ahora += 1
                tok += r.tokens_entrada + r.tokens_salida
                costo += r.costo_usd
                marca = "ABST" if r.abstencion else ("MAXPASOS" if r.error else "ok")
                print(f"[{n}/{len(pendientes)}] {t.id_pregunta} {t.configuracion} r{t.repeticion}  {marca:8} "
                      f"{r.tiempo_s:5.1f} s  {r.tokens_entrada + r.tokens_salida:6} tok  pasos {len(r.pasos)}"
                      + (f"  (reintentos {r.reintentos}: {r.tiempo_perdido_s:.0f} s perdidos)" if r.reintentos else ""))
                if args.pausa:
                    time.sleep(args.pausa)
        except KeyboardInterrupt:
            print("\nInterrumpido. Vuelva a ejecutar el mismo comando para continuar.")

        faltan = len(tareas) - len(completadas(admin, args.lote))
        if faltan == 0:
            admin.execute("UPDATE eval.lote SET fin = now() WHERE nombre = %s AND fin IS NULL", (args.lote,))
            admin.commit()
        print(f"\nEn esta corrida: {hechas_ahora} ejecuciones · {tok} tokens · US$ {costo:.4f} (precio de lista)")
        print("Lote completo." if faltan == 0 else f"Faltan {faltan} tareas del lote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
