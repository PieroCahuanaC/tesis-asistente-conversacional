"""Análisis estadístico de la sección 3.6 sobre un lote calificado: tablas, pruebas y figuras del Cap. IV.

Uso:  python scripts/analizar_lote.py --lote principal
      python scripts/analizar_lote.py --lote principal --estabilidad estabilidad
      python scripts/analizar_lote.py --csv ruta/calificacion_automatica.csv --salida carpeta   (sin base)

Antes:  python scripts/calificar_lote.py --lote <lote>
Salida: reports/lotes/<lote>/estadistica/  (resumen.md, tablas .csv, figuras .png)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from asistente.config import RAIZ, commit_actual  # noqa: E402
from asistente.evaluacion import estadistica as E  # noqa: E402

AZUL, TINTA, TINTA2, REJILLA = "#2a78d6", "#0b0b0b", "#52514e", "#e4e3df"

CONSULTA = """
SELECT b.id_pregunta, b.configuracion, b.repeticion, p.tipo_consulta AS tipo, p.dificultad, k.correcta, k.abstencion,
       coalesce(k.con_cifras, false) AS con_cifras, k.cifras_no_sustentadas, b.tiempo_s::float AS tiempo_s,
       (b.tokens_entrada + b.tokens_salida) AS tokens, b.costo_usd::float AS costo_usd, b.respuesta
FROM eval.calificacion k JOIN auditoria.bitacora b USING (id_ejecucion) JOIN eval.pregunta p USING (id_pregunta)
WHERE b.lote = %s AND k.calificador = 'automatico'
"""


def leer_lote(lote: str) -> pd.DataFrame:
    from asistente.db.conexion import conectar_admin
    with conectar_admin() as c:
        cur = c.execute(CONSULTA, (lote,))
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    if df.empty:
        raise SystemExit(f"El lote «{lote}» no tiene calificaciones: ejecute scripts/calificar_lote.py --lote {lote}")
    return df


def _n(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _g(x: float) -> str:
    return f"{x:.4g}".replace(".", ",")


def _pct(x: float) -> str:
    return f"{100 * x:.1f} %".replace(".", ",")


def _estilo(ax):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(REJILLA)
    ax.tick_params(colors=TINTA2, labelsize=9)
    ax.yaxis.grid(True, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)


def figura_exactitud(tabla: pd.DataFrame, ruta: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=200)
    x = range(len(tabla))
    p = tabla.exactitud.values
    err = [p - tabla.ic95_inf.values, tabla.ic95_sup.values - p]
    ax.bar(x, p, width=0.5, color=AZUL, zorder=2)
    ax.errorbar(x, p, yerr=err, fmt="none", ecolor=TINTA, elinewidth=1.2, capsize=5, zorder=3)
    ax.axhline(E.UMBRAL_HE4, color=TINTA2, linestyle="--", linewidth=1, zorder=1)
    ax.text(-0.42, E.UMBRAL_HE4 + 0.02, "umbral 0,80 (HE4)", color=TINTA2, fontsize=8, ha="left")
    for i, v in enumerate(p):                       # valor dentro de la barra: no choca con el IC ni el umbral
        if v >= 0.12:
            ax.text(i, v / 2, _pct(v), ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        else:
            ax.text(i, tabla.ic95_sup.iloc[i] + 0.03, _pct(v), ha="center", color=TINTA, fontsize=9)
    ax.set_xticks(list(x), tabla.configuracion)
    ax.set_ylim(0, 1.08)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(round(100 * v))} %"))
    ax.set_ylabel("Exactitud", color=TINTA2, fontsize=9)
    _estilo(ax)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def figura_tiempos(df: pd.DataFrame, ruta: Path) -> None:
    fig, ax = plt.subplots(figsize=(6, 3.6), dpi=200)
    configs = sorted(df.configuracion.unique())
    datos = [df[df.configuracion == c].tiempo_s.values for c in configs]
    ax.boxplot(datos, tick_labels=configs, widths=0.45, patch_artist=True, showfliers=True,
               boxprops={"facecolor": "#cfe0f6", "edgecolor": AZUL, "linewidth": 1.2},
               medianprops={"color": TINTA, "linewidth": 1.6}, whiskerprops={"color": AZUL},
               capprops={"color": AZUL}, flierprops={"marker": "o", "markersize": 3, "markeredgecolor": TINTA2})
    ax.set_ylabel("Tiempo de respuesta (s)", color=TINTA2, fontsize=9)
    _estilo(ax)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def analizar(df: pd.DataFrame, salida: Path, titulo: str, df_estab: pd.DataFrame | None = None) -> str:
    salida.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for col in ("correcta", "abstencion", "con_cifras"):
        df[col] = df[col].astype(str).str.lower().isin(["true", "1", "t"])
    principal = df[df.repeticion == 1]

    ex = E.exactitud(principal)
    ex_tipo = E.exactitud(principal, "tipo")
    ex_dif = E.exactitud(principal, "dificultad")
    abst = E.abstencion_t7(principal)
    cns = E.cifras_no_sustentadas(principal)
    cont = E.continuas(principal)
    for nombre, t in [("exactitud", ex), ("exactitud_por_tipo", ex_tipo), ("exactitud_por_dificultad", ex_dif),
                      ("abstencion_t7", abst), ("cifras_no_sustentadas", cns), ("tiempo_tokens_costo", cont)]:
        t.to_csv(salida / f"{nombre}.csv", index=False, encoding="utf-8-sig")

    m = E.matriz_pareada(principal)
    pruebas = []
    if set(E.CONFIGS) <= set(m.columns):
        pruebas.append(E.he1_cochran(m))
        pruebas += E.he2_he3(m)
    if "C3" in principal.configuracion.unique():
        pruebas.append(E.he4_binomial(principal))
    pd.DataFrame([p.__dict__ for p in pruebas]).to_csv(salida / "hipotesis.csv", index=False, encoding="utf-8-sig")
    continuas = [E.comparar_continua(principal, v) for v in ("tiempo_s", "tokens", "costo_usd")] \
        if principal.configuracion.nunique() >= 2 else []
    (salida / "continuas.json").write_text(json.dumps(continuas, ensure_ascii=False, indent=2), encoding="utf-8")

    figura_exactitud(ex, salida / "fig_exactitud.png")
    figura_tiempos(principal, salida / "fig_tiempos.png")

    L = [f"# Resultados — {titulo}", "", f"Commit: {commit_actual()} · respuestas: {len(principal)} · "
         f"preguntas pareadas: {len(m)}", "", "## Exactitud (IC de Wilson al 95 %)", "",
         "| Config. | Correctas | Exactitud | IC 95 % |", "|---|---|---|---|"]
    L += [f"| {r.configuracion} | {r.correctas}/{r.n} | {_pct(r.exactitud)} | [{_pct(r.ic95_inf)}; {_pct(r.ic95_sup)}] |"
          for r in ex.itertuples()]
    piv = ex_tipo.pivot(index="tipo", columns="configuracion", values="exactitud")
    L += ["", "## Exactitud por tipo de consulta", "", "| Tipo | " + " | ".join(piv.columns) + " |",
          "|---" * (len(piv.columns) + 1) + "|"]
    L += [f"| {t} | " + " | ".join(_pct(v) for v in fila) + " |" for t, fila in piv.iterrows()]
    piv = ex_dif.pivot(index="dificultad", columns="configuracion", values="exactitud")
    L += ["", "## Exactitud por dificultad", "", "| Dificultad | " + " | ".join(piv.columns) + " |",
          "|---" * (len(piv.columns) + 1) + "|"]
    L += [f"| {t} | " + " | ".join(_pct(v) for v in fila) + " |" for t, fila in piv.iterrows()]
    L += ["", "## Abstención correcta (T7) y cifras no sustentadas", "",
          "| Config. | Abstención correcta T7 | Respuestas con cifra no sustentada |", "|---|---|---|"]
    for c in ex.configuracion:
        a = abst[abst.configuracion == c]
        s = cns[cns.configuracion == c]
        ta = f"{int(a.abstenciones_correctas.iloc[0])}/{int(a.n_t7.iloc[0])} ({_pct(a.tasa.iloc[0])})" if len(a) else "—"
        ts = f"{int(s.con_cifra_no_sustentada.iloc[0])}/{int(s.respuestas_con_cifras.iloc[0])} ({_pct(s.tasa.iloc[0])})" if len(s) else "—"
        L.append(f"| {c} | {ta} | {ts} |")
    L += ["", "## Tiempo, tokens y costo por consulta", "",
          "| Config. | Media (s) | Mediana (s) | Moda (s) | DE (s) | P90 (s) | Tokens (media) | Costo medio (US$) | Costo total (US$) |",
          "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r.configuracion} | {_n(r.tiempo_media_s)} | {_n(r.tiempo_mediana_s)} | {_n(r.tiempo_moda_s, 1)} | "
          f"{_n(r.tiempo_de_s)} | {_n(r.tiempo_p90_s)} | {_n(r.tokens_media, 0)} | {_n(r.costo_media_usd, 5)} | {_n(r.costo_total_usd, 4)} |"
          for r in cont.itertuples()]
    L += ["", "## Contraste de hipótesis (α = 0,05)", "", "| Hipótesis | Prueba | p | p ajustado | Decisión | Detalle |",
          "|---|---|---|---|---|---|"]
    L += [f"| {p.hipotesis} | {p.prueba} | {_g(p.p_valor)} | {'' if p.p_ajustado is None else _g(p.p_ajustado)} | "
          f"{p.decision} | {p.detalle} |" for p in pruebas]
    if pruebas and pruebas[0].hipotesis == "HE1" and pruebas[0].p_valor >= E.ALFA:
        L += ["", "Nota: HE1 no rechaza H0; según 3.6, HE2 y HE3 se informan solo como descriptivas."]
    for c in continuas:
        L += ["", f"### {c['variable']}: {c['prueba']}", "",
              "Normalidad (Kolmogorov-Smirnov con corrección de Lilliefors): " + "; ".join(
                  f"{k}: p = {_g(v[1])}" for k, v in c["normalidad_ks"].items()),
              f"Estadístico = {_g(c['estadistico'])}; p = {_g(c['p_valor'])} → {c['decision']}"]
        L += [f"- {x['par']}: p Holm = {_g(x['p_holm'])} (mediana de la diferencia = {_g(x['mediana_dif'])})"
              for x in c["pares"]]
    if df_estab is not None and len(df_estab):
        for col in ("correcta",):
            df_estab[col] = df_estab[col].astype(str).str.lower().isin(["true", "1", "t"])
        est = E.estabilidad(df_estab)
        L += ["", "## Estabilidad", "", f"{est['preguntas']} preguntas × {est['repeticiones']} repeticiones: "
              f"calificación idéntica en {_pct(est['coincide_calificacion'])} de las preguntas"
              + (f"; texto idéntico en {_pct(est['coincide_texto_identico'])}." if "coincide_texto_identico" in est else ".")]
    L += ["", "Figuras: fig_exactitud.png (exactitud con IC de Wilson y umbral de HE4), fig_tiempos.png (diagrama de caja)."]
    texto = "\n".join(L) + "\n"
    (salida / "resumen.md").write_text(texto, encoding="utf-8")
    return texto


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote")
    ap.add_argument("--estabilidad", help="lote de repeticiones (etapa 5)")
    ap.add_argument("--csv")
    ap.add_argument("--salida")
    a = ap.parse_args()
    if a.csv:
        df = pd.read_csv(a.csv)
        salida = Path(a.salida or Path(a.csv).parent / "estadistica")
        titulo = Path(a.csv).stem
    elif a.lote:
        df = leer_lote(a.lote)
        salida = RAIZ / "reports" / "lotes" / a.lote / "estadistica"
        titulo = f"lote «{a.lote}»"
    else:
        raise SystemExit("Indique --lote o --csv")
    df_estab = leer_lote(a.estabilidad) if a.estabilidad else None
    print(analizar(df, salida, titulo, df_estab))
    print(f"Archivos en: {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
