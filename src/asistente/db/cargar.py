"""Carga idempotente de las órdenes del PTE en datos.orden (RF-01: sin duplicar las ya cargadas)."""
from __future__ import annotations

import json

import pandas as pd
import psycopg

from asistente.config import commit_actual

COLUMNAS_ORDEN = [
    "id_registro", "tipo_orden", "numero_orden", "tipo_contratacion", "codigo_finalidad",
    "nombre_finalidad_pte", "con_codigo", "tipo_gasto", "expediente_siaf", "fecha_emision",
    "fecha_compromiso", "estado", "monto_soles", "ruc_proveedor", "persona_natural", "razon_social",
    "monto_uit", "anio", "mes", "deviene_seleccion", "supera_8_uit", "incluida", "estado_confiable",
    "archivo_origen", "fila_origen",
]


def _nativo(v):
    """Convierte NaN/NaT y tipos numpy a valores que psycopg entiende."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def cargar_ordenes(conn: psycopg.Connection, ordenes: pd.DataFrame, manifiesto: pd.DataFrame,
                   fecha_corte=None) -> int:
    """Inserta o actualiza las órdenes; devuelve el id_carga registrado."""
    archivos = manifiesto[["archivo", "sha256", "filas"]].to_dict("records")
    with conn.transaction():
        id_carga = conn.execute(
            "INSERT INTO datos.carga (fuente, fecha_corte, archivos, filas, commit_codigo) "
            "VALUES ('PTE', %s, %s, %s, %s) RETURNING id_carga",
            (fecha_corte, json.dumps(archivos), len(ordenes), commit_actual()),
        ).fetchone()[0]

        # Catálogo de finalidades: el nombre del PTE más frecuente para cada código.
        catalogo = (ordenes.dropna(subset=["codigo_finalidad"])
                    .groupby("codigo_finalidad")["nombre_finalidad_pte"]
                    .agg(lambda s: s.value_counts().index[0] if s.notna().any() else None))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO datos.finalidad (codigo_finalidad, nombre_pte) VALUES (%s, %s) "
                "ON CONFLICT (codigo_finalidad) DO UPDATE SET nombre_pte = EXCLUDED.nombre_pte",
                list(catalogo.items()),
            )

            cols = COLUMNAS_ORDEN + ["id_carga"]
            actualizar = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id_registro")
            consulta = (f"INSERT INTO datos.orden ({', '.join(cols)}) "
                        f"VALUES ({', '.join(['%s'] * len(cols))}) "
                        f"ON CONFLICT (tipo_orden, numero_orden, anio) DO UPDATE SET {actualizar}")
            filas = [[_nativo(v) for v in fila] + [id_carga]
                     for fila in ordenes[COLUMNAS_ORDEN].itertuples(index=False, name=None)]
            cur.executemany(consulta, filas)
    return id_carga
