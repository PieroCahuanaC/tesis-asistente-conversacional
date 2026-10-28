"""Ingesta de las órdenes de compra y de servicio del Portal de Transparencia Estándar (RF-01 a RF-03).

Entrada : data/raw/pte/AAAA/PTE_AAAA_MM_MES.xls (archivos tal como se descargaron).
Salida  : DataFrame con la estructura de la Ficha 1 (Anexo 1), el manifiesto de archivos
          (sha256 y metadatos) y el embudo de limpieza (pérdidas por paso).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import olefile
import pandas as pd
import xlrd

from asistente.config import RAIZ, ajustes
from asistente.ingesta import limpieza as L

COLUMNAS_PTE = [
    "N°", "Tipo de Orden", "Número de orden", "Tipo de Contratación",
    "Descripción y Finalidad de la contratación", "Nro. Exp. SIAF", "Fecha de Emisión",
    "Fecha de Compromiso", "Estado", "Monto", "RUC", "Denominación o razón Social",
]
_RE_NOMBRE = re.compile(r"PTE_(\d{4})_(\d{2})_[A-Z]+\.xls$")


@dataclass
class ResultadoIngesta:
    ordenes: pd.DataFrame
    manifiesto: pd.DataFrame
    embudo: pd.DataFrame
    advertencias: list[str] = field(default_factory=list)


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _metadatos_ole(ruta: Path) -> dict:
    """Detecta si el .xls fue guardado de nuevo en Excel (los originales del portal no traen autor)."""
    try:
        with olefile.OleFileIO(str(ruta)) as ole:
            meta = ole.get_metadata()
        autor = (meta.last_saved_by or b"").decode("latin-1").strip() or None
        app = (meta.creating_application or b"").decode("latin-1").strip() or None
        guardado = meta.last_saved_time.isoformat() if meta.last_saved_time else None
    except Exception:
        autor = app = guardado = None
    return {"ultimo_guardado_por": autor, "aplicacion": app, "fecha_ultimo_guardado": guardado,
            "regrabado_en_excel": autor is not None}


def leer_archivo(ruta: Path) -> pd.DataFrame:
    """Lee un .xls mensual del PTE sin interpretar tipos (todo como texto)."""
    hoja = xlrd.open_workbook(str(ruta)).sheet_by_index(0)
    cabecera = [str(c).strip() for c in hoja.row_values(0)]
    if [c[:30] for c in cabecera] != [c[:30] for c in COLUMNAS_PTE]:
        raise ValueError(f"{ruta.name}: cabecera inesperada {cabecera}")
    filas = [[str(v) for v in hoja.row_values(i)] for i in range(1, hoja.nrows)]
    df = pd.DataFrame(filas, columns=COLUMNAS_PTE, dtype="object")
    df["archivo_origen"] = ruta.name
    df["fila_origen"] = range(2, hoja.nrows + 1)  # fila en Excel (1 = cabecera)
    return df


def listar_archivos(directorio: Path | None = None) -> list[Path]:
    directorio = directorio or RAIZ / "data" / "raw" / "pte"
    archivos = sorted(p for p in directorio.glob("*/*.xls") if _RE_NOMBRE.search(p.name))
    if not archivos:
        raise FileNotFoundError(f"No hay archivos PTE_AAAA_MM_MES.xls en {directorio}")
    return archivos


def construir_ordenes(directorio: Path | None = None, clave_seudonimo: str | None = None) -> ResultadoIngesta:
    cfg = ajustes()
    uit = {int(k): Decimal(str(v)) for k, v in cfg["uit"].items()}
    tramo = cfg["tramo_sin_codigo_ni_estado"]
    prefijos_pn = [str(p) for p in cfg["ruc_persona_natural"]]
    if clave_seudonimo is None:
        from asistente.config import env
        clave_seudonimo = env("SEUDONIMO_CLAVE")

    archivos = listar_archivos(directorio)
    advertencias: list[str] = []
    manifiesto, crudos = [], []
    for ruta in archivos:
        anio_arch, mes_arch = map(int, _RE_NOMBRE.search(ruta.name).groups())
        df = leer_archivo(ruta)
        df["anio_archivo"], df["mes_archivo"] = anio_arch, mes_arch
        crudos.append(df)
        manifiesto.append({"archivo": ruta.name, "anio": anio_arch, "mes": mes_arch,
                           "sha256": _sha256(ruta), "bytes": ruta.stat().st_size,
                           "filas": len(df), **_metadatos_ole(ruta)})
    crudo = pd.concat(crudos, ignore_index=True)

    registros = []
    for r in crudo.to_dict("records"):
        tipo = L.normalizar_tipo_orden(r["Tipo de Orden"])
        numero = int(float(r["Número de orden"]))
        f_emi = L.parsear_fecha(r["Fecha de Emisión"])
        monto = L.parsear_monto(r["Monto"])
        codigo, nombre_pte = L.extraer_finalidad(r["Descripción y Finalidad de la contratación"])
        ruc = L.normalizar_ruc(r["RUC"])
        natural = L.es_persona_natural(ruc, prefijos_pn)
        t_cont = L.normalizar_tipo_contratacion(r["Tipo de Contratación"])
        anio, mes = f_emi.year, f_emi.month
        tope = 8 * uit[anio]
        registros.append({
            "id_registro": f"{anio}-{tipo.replace('/', '')}-{numero:05d}",
            "tipo_orden": tipo,
            "numero_orden": numero,
            "tipo_contratacion": t_cont,
            "codigo_finalidad": codigo,
            "nombre_finalidad_pte": nombre_pte,
            "con_codigo": codigo is not None,
            "tipo_gasto": None,  # se completa con la Consulta Amigable (corriente / inversión)
            "expediente_siaf": L.limpiar_texto(r["Nro. Exp. SIAF"]),
            "fecha_emision": f_emi,
            "fecha_compromiso": L.parsear_fecha(r["Fecha de Compromiso"]),
            "estado": L.normalizar_estado(r["Estado"]),
            "monto_soles": monto,
            "ruc_proveedor": L.seudonimizar(ruc, clave_seudonimo) if natural else ruc,
            "persona_natural": natural,
            "razon_social": None if natural else L.limpiar_texto(r["Denominación o razón Social"]),
            "monto_uit": (monto / uit[anio]).quantize(Decimal("0.0001")),
            "anio": anio,
            "mes": mes,
            "deviene_seleccion": t_cont == "deviene_seleccion",
            "supera_8_uit": monto > tope,
            "incluida": (t_cont != "deviene_seleccion") and monto <= tope,
            "estado_confiable": not L.en_tramo(anio, mes, tramo["desde"], tramo["hasta"]),
            "archivo_origen": r["archivo_origen"],
            "fila_origen": r["fila_origen"],
            "_mes_archivo_coincide": (anio, mes) == (r["anio_archivo"], r["mes_archivo"]),
        })
    ordenes = pd.DataFrame(registros)

    n_fuera = int((~ordenes["_mes_archivo_coincide"]).sum())
    if n_fuera:
        advertencias.append(f"{n_fuera} órdenes con fecha de emisión fuera del mes de su archivo")
    ordenes = ordenes.drop(columns="_mes_archivo_coincide")

    # Duplicados por (tipo, número, año): se conserva la primera aparición (RF-01).
    dup = ordenes.duplicated(["tipo_orden", "numero_orden", "anio"], keep="first")
    if dup.any():
        advertencias.append(f"{int(dup.sum())} duplicados por (tipo, número, año) descartados")
    ordenes = ordenes[~dup].reset_index(drop=True)

    sin_cod_fuera_tramo = ordenes[(~ordenes.con_codigo) & ordenes.estado_confiable & ordenes.incluida]
    if len(sin_cod_fuera_tramo):
        advertencias.append(f"{len(sin_cod_fuera_tramo)} órdenes incluidas sin código fuera del tramo R-05: "
                            + ", ".join(sin_cod_fuera_tramo.id_registro.head(10)))

    embudo = pd.DataFrame([
        ("Filas leídas de los archivos", len(crudo)),
        ("Sin duplicados (tipo, número, año)", len(ordenes)),
        ("Excluidas: derivan de procedimiento de selección", -int(ordenes.deviene_seleccion.sum())),
        ("Excluidas: superan 8 UIT (sin marca de selección)",
         -int((ordenes.supera_8_uit & ~ordenes.deviene_seleccion).sum())),
        ("Órdenes incluidas (<= 8 UIT)", int(ordenes.incluida.sum())),
        ("De ellas, anuladas (identificables)", int((ordenes.incluida & (ordenes.estado == "anulada")).sum())),
        ("Órdenes incluidas sin anuladas", int((ordenes.incluida & (ordenes.estado != "anulada")).sum())),
    ], columns=["paso", "ordenes"])

    return ResultadoIngesta(ordenes=ordenes, manifiesto=pd.DataFrame(manifiesto),
                            embudo=embudo, advertencias=advertencias)
