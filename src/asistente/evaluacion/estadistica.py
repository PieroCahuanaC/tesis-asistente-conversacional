"""Plan de análisis estadístico de la sección 3.6 (etapa 6 de 3.5.4).

Entrada: un DataFrame con una fila por respuesta calificada (columnas de calificacion_automatica.csv).
  Descriptiva: exactitud global, por tipo y por dificultad con IC de Wilson al 95 %; abstención correcta
  en T7; tasa de cifras no sustentadas; tiempo (media, mediana, moda, DE, P90), tokens y costo.
  Inferencial (α = 0,05):
    HE1  Q de Cochran (C1, C2, C3)
    HE2  McNemar unilateral C3 > C1   } corrección de Holm entre las dos
    HE3  McNemar unilateral C2 > C1   }
    HE4  binomial exacta unilateral pC3 > 0,80, con IC de Wilson
  Tiempo, tokens y costo: Kolmogorov-Smirnov (Lilliefors) por configuración; si todas son normales,
  ANOVA de medidas repetidas; si no, Friedman y Wilcoxon por pares con Holm.
  Estabilidad: proporción de preguntas cuyas repeticiones coinciden. Concordancia: kappa de Cohen.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.anova import AnovaRM
from statsmodels.stats.contingency_tables import cochrans_q
from statsmodels.stats.diagnostic import lilliefors
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

ALFA = 0.05
UMBRAL_HE4 = 0.80
CONFIGS = ["C1", "C2", "C3"]


def wilson(k: int, n: int) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"),) * 3
    lo, hi = proportion_confint(k, n, alpha=ALFA, method="wilson")
    return k / n, float(lo), float(hi)


# ------------------------------------------------------------------ descriptiva

def exactitud(df: pd.DataFrame, por: str | None = None) -> pd.DataFrame:
    grupos = ["configuracion"] + ([por] if por else [])
    filas = []
    for clave, g in df.groupby(grupos):
        clave = clave if isinstance(clave, tuple) else (clave,)
        p, lo, hi = wilson(int(g.correcta.sum()), len(g))
        filas.append(dict(zip(grupos, clave)) | {"correctas": int(g.correcta.sum()), "n": len(g),
                                                  "exactitud": p, "ic95_inf": lo, "ic95_sup": hi})
    return pd.DataFrame(filas)


def abstencion_t7(df: pd.DataFrame) -> pd.DataFrame:
    t7 = df[df.tipo == "T7"]
    filas = []
    for c, g in t7.groupby("configuracion"):
        p, lo, hi = wilson(int(g.abstencion.sum()), len(g))
        filas.append({"configuracion": c, "abstenciones_correctas": int(g.abstencion.sum()), "n_t7": len(g),
                      "tasa": p, "ic95_inf": lo, "ic95_sup": hi})
    return pd.DataFrame(filas)


def cifras_no_sustentadas(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for c, g in df.groupby("configuracion"):
        con = g[g.con_cifras & ~g.abstencion]
        k = int((con.cifras_no_sustentadas > 0).sum())
        p, lo, hi = wilson(k, len(con))
        filas.append({"configuracion": c, "respuestas_con_cifras": len(con), "con_cifra_no_sustentada": k,
                      "tasa": p, "ic95_inf": lo, "ic95_sup": hi})
    return pd.DataFrame(filas)


def continuas(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for c, g in df.groupby("configuracion"):
        t = g.tiempo_s
        moda = t.round(1).mode()
        filas.append({"configuracion": c, "tiempo_media_s": t.mean(), "tiempo_mediana_s": t.median(),
                      "tiempo_moda_s": float(moda.iloc[0]) if len(moda) else np.nan, "tiempo_de_s": t.std(ddof=1),
                      "tiempo_p90_s": t.quantile(0.9), "tokens_media": g.tokens.mean(),
                      "costo_media_usd": g.costo_usd.mean(), "costo_total_usd": g.costo_usd.sum()})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ inferencial

def matriz_pareada(df: pd.DataFrame, valor: str = "correcta", configs=CONFIGS) -> pd.DataFrame:
    """Preguntas × configuraciones (solo preguntas respondidas en todas: muestras relacionadas)."""
    m = df[df.repeticion == 1].pivot_table(index="id_pregunta", columns="configuracion", values=valor, aggfunc="first")
    return m[[c for c in configs if c in m.columns]].dropna()


@dataclass
class Prueba:
    hipotesis: str
    prueba: str
    estadistico: float
    p_valor: float
    p_ajustado: float | None
    decision: str
    detalle: str


def _decision(p: float) -> str:
    return "se rechaza H0" if p < ALFA else "no se rechaza H0"


def he1_cochran(m: pd.DataFrame) -> Prueba:
    x = m.astype(int).values
    if (x == x[:, :1]).all():                      # ninguna pregunta discordante: Q = 0
        return Prueba("HE1", "Q de Cochran", 0.0, 1.0, None, _decision(1.0), f"gl = {x.shape[1] - 1}; n = {len(m)} preguntas")
    r = cochrans_q(x)
    return Prueba("HE1", "Q de Cochran", float(r.statistic), float(r.pvalue), None, _decision(r.pvalue),
                  f"gl = {int(r.df)}; n = {len(m)} preguntas")


def mcnemar_unilateral(m: pd.DataFrame, mejor: str, base: str) -> tuple[float, int, int]:
    """H1: p(mejor) > p(base). Binomial exacta sobre los pares discordantes."""
    b = int(((m[mejor] == 1) & (m[base] == 0)).sum())     # mejor acierta, base falla
    c = int(((m[mejor] == 0) & (m[base] == 1)).sum())
    p = stats.binomtest(b, b + c, 0.5, alternative="greater").pvalue if b + c else 1.0
    return float(p), b, c


def he2_he3(m: pd.DataFrame) -> list[Prueba]:
    p2, b2, c2 = mcnemar_unilateral(m, "C3", "C1")
    p3, b3, c3 = mcnemar_unilateral(m, "C2", "C1")
    _, adj, _, _ = multipletests([p2, p3], alpha=ALFA, method="holm")
    return [Prueba("HE2", "McNemar unilateral C3 > C1 (Holm)", float(b2), p2, float(adj[0]), _decision(adj[0]),
                   f"discordantes: C3 bien y C1 mal = {b2}; C3 mal y C1 bien = {c2}"),
            Prueba("HE3", "McNemar unilateral C2 > C1 (Holm)", float(b3), p3, float(adj[1]), _decision(adj[1]),
                   f"discordantes: C2 bien y C1 mal = {b3}; C2 mal y C1 bien = {c3}")]


def he4_binomial(df: pd.DataFrame, config: str = "C3") -> Prueba:
    g = df[(df.configuracion == config) & (df.repeticion == 1)]
    k, n = int(g.correcta.sum()), len(g)
    r = stats.binomtest(k, n, UMBRAL_HE4, alternative="greater")
    p, lo, hi = wilson(k, n)
    return Prueba("HE4", f"Binomial exacta unilateral p{config} > {UMBRAL_HE4:.2f}".replace(".", ","), p,
                  float(r.pvalue), None, _decision(r.pvalue),
                  f"{k}/{n} correctas; IC de Wilson 95 % [{lo:.3f}; {hi:.3f}]".replace(".", ","))


def comparar_continua(df: pd.DataFrame, variable: str) -> dict:
    m = matriz_pareada(df, variable)
    normal = {}
    for c in m.columns:
        x = m[c].astype(float)
        if x.std(ddof=1) == 0:
            normal[c] = (np.nan, 0.0)
            continue
        stat, p = lilliefors(x, dist="norm")
        normal[c] = (float(stat), float(p))
    todas_normales = all(p >= ALFA for _, p in normal.values())
    salida = {"variable": variable, "n": len(m), "normalidad_ks": normal}
    if todas_normales:
        largo = m.reset_index().melt(id_vars="id_pregunta", var_name="configuracion", value_name=variable)
        r = AnovaRM(largo, variable, "id_pregunta", within=["configuracion"]).fit().anova_table
        salida |= {"prueba": "ANOVA de medidas repetidas", "estadistico": float(r["F Value"].iloc[0]),
                   "p_valor": float(r["Pr > F"].iloc[0]), "pares": []}
    elif (m.astype(float).values == m.astype(float).values[:, :1]).all():
        salida |= {"prueba": "sin variación entre configuraciones", "estadistico": 0.0, "p_valor": 1.0, "pares": []}
    else:
        s, p = stats.friedmanchisquare(*[m[c].astype(float) for c in m.columns])
        pares = list(combinations(m.columns, 2))
        crudos = []
        for a, b in pares:
            d = m[a].astype(float) - m[b].astype(float)
            crudos.append(1.0 if (d == 0).all() else float(stats.wilcoxon(m[a].astype(float), m[b].astype(float)).pvalue))
        _, adj, _, _ = multipletests(crudos, alpha=ALFA, method="holm")
        salida |= {"prueba": "Friedman + Wilcoxon por pares (Holm)", "estadistico": float(s), "p_valor": float(p),
                   "pares": [{"par": f"{a} vs {b}", "p": pc, "p_holm": float(pa),
                              "mediana_dif": float((m[a] - m[b]).median())}
                             for (a, b), pc, pa in zip(pares, crudos, adj)]}
    salida["decision"] = _decision(salida["p_valor"])
    return salida


# ------------------------------------------------------------------ estabilidad y concordancia

def estabilidad(df: pd.DataFrame) -> dict:
    """Preguntas con todas sus repeticiones calificadas igual (y, si existe, con la misma respuesta)."""
    g = df.groupby("id_pregunta")
    reps = g.repeticion.nunique()
    validas = reps[reps >= 2].index
    sub = df[df.id_pregunta.isin(validas)]
    coincide_calif = sub.groupby("id_pregunta").correcta.nunique() == 1
    res = {"preguntas": len(validas), "repeticiones": int(reps.max()) if len(reps) else 0,
           "coincide_calificacion": float(coincide_calif.mean()) if len(validas) else float("nan")}
    if "respuesta" in sub.columns:
        coincide_texto = sub.groupby("id_pregunta").respuesta.nunique() == 1
        res["coincide_texto_identico"] = float(coincide_texto.mean()) if len(validas) else float("nan")
    return res


def kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(int).values, b.astype(int).values
    po = float((a == b).mean())
    pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)
