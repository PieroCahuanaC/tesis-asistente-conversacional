"""Crea o actualiza un usuario del asistente (RF-18).

Uso:  python scripts/crear_usuario.py --usuario pcahuana --nombre "Piero Cahuana" --perfil administrador
      (pide la clave sin mostrarla)
Perfiles: jefatura (asistente, evaluación y panel), area_usuaria (asistente y evaluación),
          administrador (todo, más elegir C1/C2/C3 y ver la bitácora completa).
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asistente.api.seguridad import PERFILES, hash_clave  # noqa: E402
from asistente.db.conexion import conectar_admin  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--perfil", required=True, choices=PERFILES)
    ap.add_argument("--desactivar", action="store_true")
    a = ap.parse_args()
    clave = None
    if not a.desactivar:
        clave = getpass.getpass("Clave (mínimo 8 caracteres): ")
        if len(clave) < 8 or clave != getpass.getpass("Repita la clave: "):
            raise SystemExit("Las claves no coinciden o tienen menos de 8 caracteres")
    with conectar_admin() as c:
        if a.desactivar:
            c.execute("UPDATE auditoria.usuario SET activo = false WHERE usuario = %s", (a.usuario.lower(),))
        else:
            c.execute("""INSERT INTO auditoria.usuario (usuario, nombre, perfil, clave_hash) VALUES (%s, %s, %s, %s)
                         ON CONFLICT (usuario) DO UPDATE SET nombre = EXCLUDED.nombre, perfil = EXCLUDED.perfil,
                             clave_hash = EXCLUDED.clave_hash, activo = true""",
                      (a.usuario.lower(), a.nombre, a.perfil, hash_clave(clave)))
        c.commit()
    print(f"Usuario {a.usuario.lower()} {'desactivado' if a.desactivar else f'listo (perfil {a.perfil})'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
