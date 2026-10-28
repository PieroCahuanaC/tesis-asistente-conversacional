"""Carga de configuración (config/settings.yaml) y de variables de entorno (.env)."""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")


@lru_cache(maxsize=1)
def ajustes() -> dict:
    with open(RAIZ / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(nombre: str, obligatorio: bool = True) -> str | None:
    valor = os.getenv(nombre)
    if obligatorio and not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (ver .env.example)")
    return valor


def commit_actual() -> str:
    """Hash del commit de git que produce un resultado (RNF-11). 'sin-git' si no aplica."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=RAIZ,
                             capture_output=True, text=True, check=True).stdout.strip()
        sucio = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=RAIZ,
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + ("-modificado" if sucio else "")
    except Exception:
        return "sin-git"
