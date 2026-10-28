"""Ingesta de la ejecución presupuestal de la Consulta Amigable del MEF (RF-04, Ficha 2).

Fuente: CSV de datos abiertos del MEF «Presupuesto y Ejecución de Gasto», filtrados a Uchumayo
con scripts/filtrar_mef.py. Estructura observada (diagnóstico S1):
  - MES_EJE = 0      -> filas de marco anual: MONTO_PIA y MONTO_PIM (PIM vigente a la descarga)
  - MES_EJE = 1..12  -> flujos del mes: certificación, compromiso anual y mensual, devengado y
                        girado (pueden ser negativos por rebajas o anulaciones)
  - FINALIDAD (7 dígitos) es el código que aparece en las órdenes del PTE; SEC_FUNC es el número de
    meta del año. Una finalidad puede tener varias metas en un mismo año.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pandas as pd

from asistente.config import RAIZ, ajustes

MONTOS = {
    "MONTO_PIA": "pia",
    "MONTO_PIM": "pim",
    "MONTO_CERTIFICADO": "certificado",
    "MONTO_COMPROMETIDO_ANUAL": "comprometido_anual",
    "MONTO_COMPROMETIDO": "comprometido_mensual",
    "MONTO_DEVENGADO": "devengado",
    "MONTO_GIRADO": "girado",
}


@dataclass
class ResultadoMEF:
    ejecucion: pd.DataFrame
    finalidades: pd.DataFrame
    manifiesto: pd.DataFrame
    advertencias: list[str] = field(default_factory=list)


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _texto(s: pd.Series) -> pd.Series:
    return s.fillna("").str.strip().str.replace(r"\s+", " ", regex=True).replace("", None)


def leer_anio(ruta: Path, anio: int, sec_ejec: str) -> pd.DataFrame:
    crudo = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8")
    df = crudo[crudo["SEC_EJEC"] == sec_ejec].copy()
    if df.empty:
        raise ValueError(f"{ruta.name}: no hay filas de la ejecutora {sec_ejec}")
    if set(df["ANO_EJE"]) != {str(anio)}:
        raise ValueError(f"{ruta.name}: años inesperados {sorted(set(df['ANO_EJE']))}")
    salida = pd.DataFrame({
        "anio": anio,
        "mes": df["MES_EJE"].astype(int),
        "sec_func": df["SEC_FUNC"].astype(int),
        "finalidad": df["FINALIDAD"].str.zfill(7),
        "nombre_meta": _texto(df["META_NOMBRE"]),
        "tipo_act_proy": df["TIPO_ACT_PROY_NOMBRE"].str.strip().str.lower(),
        "producto_proyecto": _texto(df["PRODUCTO_PROYECTO"]),
        "producto_proyecto_nombre": _texto(df["PRODUCTO_PROYECTO_NOMBRE"]),
        "actividad_nombre": _texto(df["ACTIVIDAD_ACCION_OBRA_NOMBRE"]),
        "funcion_nombre": _texto(df["FUNCION_NOMBRE"]),
        "categoria_gasto": _texto(df["CATEGORIA_GASTO_NOMBRE"]).str.lower(),
        "fuente_financiamiento": _texto(df["FUENTE_FINANCIAMIENTO_NOMBRE"]),
        "rubro": _texto(df["RUBRO_NOMBRE"]),
        "generica_nombre": _texto(df["GENERICA_NOMBRE"]),
        "clasificador": (df["TIPO_TRANSACCION"] + "." + df["GENERICA"] + "." + df["SUBGENERICA"] + "."
                         + df["SUBGENERICA_DET"] + "." + df["ESPECIFICA"] + "." + df["ESPECIFICA_DET"]),
        "clasificador_nombre": _texto(df["ESPECIFICA_DET_NOMBRE"]),
    })
    for origen, destino in MONTOS.items():
        salida[destino] = df[origen].map(lambda v: Decimal(v) if v else Decimal(0))
    if not salida["mes"].between(0, 12).all():
        raise ValueError(f"{ruta.name}: MES_EJE fuera de 0-12")
    marco_en_meses = salida[(salida.mes > 0) & ((salida.pia != 0) | (salida.pim != 0))]
    if len(marco_en_meses):
        raise ValueError(f"{ruta.name}: {len(marco_en_meses)} filas mensuales con PIA/PIM (se esperaba solo en MES_EJE=0)")
    return salida.reset_index(drop=True)


def construir_ejecucion(archivos: dict[int, Path] | None = None) -> ResultadoMEF:
    cfg = ajustes()["mef"]
    archivos = archivos or {int(a): RAIZ / p for a, p in cfg["archivos"].items()}
    partes, manifiesto, advertencias = [], [], []
    for anio, ruta in sorted(archivos.items()):
        parte = leer_anio(ruta, anio, str(cfg["sec_ejec"]))
        partes.append(parte)
        manifiesto.append({"archivo": ruta.name, "anio": anio, "sha256": _sha256(ruta), "filas": len(parte)})
    ejecucion = pd.concat(partes, ignore_index=True)

    # Catálogo de finalidades: nombre y tipo de gasto (proyecto -> inversión; actividad -> corriente),
    # tomando el que concentra más PIM cuando una finalidad tiene ambos.
    # Las finalidades sin fila de marco (sin PIM en el año) toman el tipo de sus filas mensuales.
    pesos = ejecucion.assign(peso=ejecucion["pim"].astype(float).abs() + 1e-6)
    tipo = (pesos.groupby(["finalidad", "tipo_act_proy"]).peso.sum().reset_index()
            .sort_values("peso", ascending=False).drop_duplicates("finalidad"))
    nombres = (ejecucion.dropna(subset=["nombre_meta"]).sort_values(["anio", "mes"])
               .drop_duplicates("finalidad", keep="last")[["finalidad", "nombre_meta"]])
    finalidades = nombres.merge(tipo[["finalidad", "tipo_act_proy"]], on="finalidad", how="left")
    finalidades["tipo_gasto"] = finalidades.tipo_act_proy.map({"proyecto": "inversion", "actividad": "corriente"})
    finalidades = finalidades.rename(columns={"nombre_meta": "nombre_mef"})[["finalidad", "nombre_mef", "tipo_gasto"]]
    finalidades = finalidades.astype(object).where(finalidades.notna(), None)

    tot = ejecucion.groupby("anio")[["pim", "certificado"]].sum()
    for anio, fila in tot.iterrows():
        if fila.certificado > fila.pim:
            advertencias.append(f"{anio}: certificación anual ({fila.certificado}) supera el PIM ({fila.pim})")
    return ResultadoMEF(ejecucion=ejecucion, finalidades=finalidades,
                        manifiesto=pd.DataFrame(manifiesto), advertencias=advertencias)
