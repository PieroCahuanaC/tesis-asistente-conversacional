"""Cálculo B de las respuestas de referencia: Python (pandas) directamente sobre los archivos fuente.

Es independiente del cálculo A y del asistente: tiene su propio lector de los .xls del PTE y de los
CSV del MEF, su propia limpieza y sus propias reglas escritas de nuevo; no usa PostgreSQL, ni el
módulo de ingesta, ni las herramientas. Si A y B coinciden, el valor de referencia es confiable.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

from asistente.config import RAIZ
from asistente.evaluacion.familias import Familia

UIT = {2023: 4950, 2024: 5150, 2025: 5350}           # D.S. de la UIT de cada año
SEC_EJEC_UCHUMAYO = "300354"
COLS_PTE = ["n", "tipo", "numero", "tcont", "desc", "siaf", "femi", "fcomp", "estado", "monto", "ruc", "razon"]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s).upper()) if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def ordenes() -> pd.DataFrame:
    partes = []
    for ruta in sorted((RAIZ / "data" / "raw" / "pte").glob("*/*.xls")):
        d = pd.read_excel(ruta, dtype=str, engine="xlrd", keep_default_na=False)
        d.columns = COLS_PTE
        partes.append(d)
    o = pd.concat(partes, ignore_index=True)
    o["monto"] = o.monto.str.replace(r"^\s*S/\.?", "", regex=True).str.replace(",", "").str.strip().astype(float)
    o["anio"] = o.femi.str[:4].astype(int)
    o["mes"] = o.femi.str[5:7].astype(int)
    o["numero"] = o.numero.astype(float).astype(int)
    o["estado"] = o.estado.str.strip().str.lower()
    o["deviene"] = o.tcont.str.strip().str.startswith("Deviene")
    o["incluida"] = (~o.deviene) & (o.monto <= o.anio.map(UIT) * 8)
    o["codigo"] = o.desc.str.extract(r"(?:^|-)\s*(\d{7})(?!\d)")[0]
    o["natural"] = o.ruc.str.strip().str[:2].isin(["10", "15", "17"])
    o = o.drop_duplicates(["tipo", "numero", "anio"])
    return o


@lru_cache(maxsize=1)
def ejecucion() -> pd.DataFrame:
    partes = []
    for ruta in sorted((RAIZ / "data" / "raw" / "mef" / "filtrado").glob("*_UCHUMAYO.csv")):
        d = pd.read_csv(ruta, dtype=str, keep_default_na=False)
        partes.append(d[d.SEC_EJEC == SEC_EJEC_UCHUMAYO])
    e = pd.concat(partes, ignore_index=True)
    out = pd.DataFrame({"anio": e.ANO_EJE.astype(int), "mes": e.MES_EJE.astype(int), "fin": e.FINALIDAD,
                        "nombre": e.META_NOMBRE})
    for c, k in [("pim", "MONTO_PIM"), ("cert", "MONTO_CERTIFICADO"), ("comp", "MONTO_COMPROMETIDO_ANUAL"),
                 ("dev", "MONTO_DEVENGADO")]:
        out[c] = pd.to_numeric(e[k], errors="coerce").fillna(0.0)
    return out


def resolver_nombre(nombre: str, anio: int) -> str:
    """Busca la finalidad cuyo nombre (MEF) contiene el texto; debe ser única en el año."""
    e = ejecucion()
    clave = _norm(nombre)
    hits = sorted(set(e[(e.anio == anio) & e.nombre.map(lambda n: clave in _norm(n))].fin))
    if len(hits) != 1:
        raise ValueError(f"«{nombre}» en {anio}: {len(hits)} finalidades coinciden")
    return hits[0]


def _r(x, d=2):
    return round(float(x), d)


def _fin(p):
    return p["fin"] if "fin" in p else resolver_nombre(p["nombre"], p["anio"])


def calcular(f: Familia) -> list[list] | None:
    p, n = f.p, f.nombre
    if n == "no_respondible":
        return None
    e, o = ejecucion(), ordenes()
    ea = e[e.anio == p.get("anio")] if "anio" in p else e

    def de_fin(fin):
        return ea[ea.fin == fin]

    if n in ("saldo", "alcanza"):
        d = de_fin(_fin(p))
        s = _r(d.pim.sum() - d[(d.mes >= 1) & (d.mes <= p["mes"])].cert.sum())
        if n == "saldo":
            return [[s]]
        dif = _r(s - p["monto"])
        return [[s, dif, "alcanza" if dif >= 0 else "no alcanza"]]
    if n == "pim":
        return [[_r(de_fin(_fin(p)).pim.sum())]]
    if n in ("cert_acum", "cert_mes"):
        d = de_fin(_fin(p))
        m = d.mes.between(1, p["mes"]) if n == "cert_acum" else d.mes == p["mes"]
        return [[_r(d[m].cert.sum())]]
    if n in ("dev_rango", "comp_trim"):
        d = de_fin(_fin(p))
        col = "dev" if n == "dev_rango" else "comp"
        return [[_r(d[d.mes.between(p["m1"], p["m2"])][col].sum())]]
    if n == "dev_total_mes":
        return [[_r(ea[ea.mes == p["mes"]].dev.sum())]]
    if n == "dev_total_anio":
        return [[_r(ea[ea.mes.between(1, 12)].dev.sum())]]
    if n in ("dev_anual_pct", "pct_dev"):
        d = de_fin(_fin(p))
        dev, pim = d[d.mes > 0].dev.sum(), d.pim.sum()
        pct = _r(100 * dev / pim)
        return [[_r(dev), pct]] if n == "dev_anual_pct" else [[pct]]

    # ---- órdenes
    oa = o[o.incluida & (o.anio == p.get("anio"))] if "anio" in p else o[o.incluida]
    if p.get("tipo"):
        oa = oa[oa.tipo == p["tipo"]]
    if n in ("ordenes_periodo", "conteo_periodo", "monto_periodo"):
        x = oa[oa.mes.between(p["m1"], p["m2"])]
        cnt, monto = len(x), _r(x[x.estado != "anulada"].monto.sum())
        return {"ordenes_periodo": [[cnt, monto]], "conteo_periodo": [[cnt]], "monto_periodo": [[monto]]}[n]
    if n == "monto_meta_mes":
        x = oa[(oa.mes == p["mes"]) & (oa.codigo == p["fin"]) & (oa.estado != "anulada")]
        return [[_r(x.monto.sum())]]
    if n == "anuladas":
        return [[int(((oa.estado == "anulada") & oa.mes.between(p["m1"], p["m2"])).sum())]]
    if n == "promedio":
        return [[_r(oa[oa.estado != "anulada"].monto.mean())]]
    if n == "superan_8uit":
        return [[int(((o.anio == p["anio"]) & (o.monto > 8 * UIT[p["anio"]])).sum())]]
    if n == "personas_naturales":
        return [[int(oa.natural.sum())]]

    # ---- rankings y comparaciones
    if n in ("top_dev", "top_dev_periodo", "top_pim", "top_saldo"):
        if n == "top_pim":
            v = ea.groupby("fin").pim.sum()
        elif n == "top_saldo":
            v = ea.groupby("fin").pim.sum() - ea[ea.mes.between(1, p["mes"])].groupby("fin").cert.sum().reindex(
                ea.fin.unique(), fill_value=0)
        else:
            m1, m2 = (p["m1"], p["m2"]) if n == "top_dev_periodo" else (1, 12)
            v = ea[ea.mes.between(m1, m2)].groupby("fin").dev.sum()
        v = v.sort_values(ascending=False).head(p["n"])
        return [[f, _r(x)] for f, x in v.items()]
    if n == "top_ordenes":
        x = oa[oa.mes.between(p["m1"], p["m2"]) & oa.codigo.notna() & (oa.estado != "anulada")]
        v = x.groupby("codigo").monto.sum().sort_values(ascending=False).head(p["n"])
        return [[f, _r(m)] for f, m in v.items()]
    if n == "bottom_avance":
        pim = ea.groupby("fin").pim.sum()
        dev = ea[ea.mes > 0].groupby("fin").dev.sum().reindex(pim.index, fill_value=0)
        av = (100 * dev[pim > 0] / pim[pim > 0]).round(2).sort_values().head(p["n"])
        return [[f, float(a)] for f, a in av.items()]
    if n == "var_dev":
        d = e[(e.fin == p["fin"]) & (e.mes > 0)]
        d1, d2 = d[d.anio == p["a1"]].dev.sum(), d[d.anio == p["a2"]].dev.sum()
        return [[_r(d2 - d1), _r(100 * (d2 - d1) / d1)]]
    if n == "var_total":
        col = "pim" if p["medida"] == "pim" else "dev"
        v1, v2 = e[e.anio == p["a1"]][col].sum(), e[e.anio == p["a2"]][col].sum()
        return [[_r(v2 - v1), _r(100 * (v2 - v1) / v1)]]
    if n == "mes_max_ordenes":
        c = oa.groupby("mes").size()
        mes = int(c[c == c.max()].index.min())
        return [[mes, int(c.max())]]
    if n == "mes_max_dev":
        v = ea[ea.mes > 0].groupby("mes").dev.sum()
        return [[int(v.idxmax()), _r(v.max())]]
    if n == "trim_max_dev":
        x = ea[ea.mes > 0]
        v = x.groupby((x.mes + 2) // 3).dev.sum()
        return [[int(v.idxmax()), _r(v.max())]]
    if n == "comp_conteo_anios":
        c1 = int((o.incluida & (o.anio == p["a1"])).sum())
        c2 = int((o.incluida & (o.anio == p["a2"])).sum())
        return [[p["a1"] if c1 >= c2 else p["a2"], abs(c1 - c2)]]
    if n == "comp_tipo_monto":
        x = oa[oa.estado != "anulada"]
        oc, os_ = x[x.tipo == "O/C"].monto.sum(), x[x.tipo == "O/S"].monto.sum()
        return [["O/C" if oc >= os_ else "O/S", _r(abs(oc - os_))]]
    if n == "comp_metas":
        col = "pim" if p["medida"] == "pim" else "dev"
        x = ea if col == "pim" else ea[ea.mes > 0]
        v1, v2 = x[x.fin == p["f1"]][col].sum(), x[x.fin == p["f2"]][col].sum()
        return [[p["f1"] if v1 >= v2 else p["f2"], _r(abs(v1 - v2))]]
    if n == "max_orden":
        x = oa[oa.estado != "anulada"].sort_values(["monto", "numero"], ascending=[False, True]).iloc[0]
        return [[int(x.numero), _r(x.monto)]]

    # ---- avance (T5)
    if n.startswith(("contar_avance", "listar_avance")) or n == "avance_meta":
        pim = ea.groupby("fin").pim.sum()
        dev = ea[ea.mes.between(1, p["mes"])].groupby("fin").dev.sum().reindex(pim.index, fill_value=0)
        av = (100 * dev[pim > 0] / pim[pim > 0]).round(2)
        if n == "avance_meta":
            a = float(av[_fin(p)])
            return [[a, "sí" if a > p["umbral"] else "no"]]
        sel = av[av > p["umbral"]] if n.endswith("mayor") else av[av < p["umbral"]]
        return [[len(sel)]] if n.startswith("contar") else [[f] for f in sorted(sel.index)]
    raise ValueError(f"Familia sin cálculo B: {n}")
