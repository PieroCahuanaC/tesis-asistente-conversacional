"""Diagnóstico de los datos del PTE (OE1): evidencia para el Capítulo IV.

Uso:  python scripts/diagnostico_pte.py
Salida en reports/diagnostico_pte/:
  embudo_limpieza.csv          pérdidas por paso de limpieza
  cobertura_mensual.csv        órdenes, cobertura del código y estado por mes
  resumen_anual.csv            órdenes, anuladas, gasto y % persona natural por año
  manifiesto_archivos.csv      sha256 y metadatos de los 36 archivos
  resumen.json                 cifras clave + commit que las produjo
  fig_cobertura_codigo.png     figura de cobertura del código de finalidad por mes
No usa la base de datos: lee directamente los archivos originales.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from asistente.config import RAIZ, ajustes, commit_actual  # noqa: E402
from asistente.ingesta.pte import construir_ordenes  # noqa: E402

SALIDA = RAIZ / "reports" / "diagnostico_pte"
# Paleta validada (dataviz: CVD y contraste OK sobre fondo claro).
AZUL, NARANJA = "#2a78d6", "#eb6834"
TINTA, TINTA_2, MUTED, FONDO = "#0b0b0b", "#52514e", "#898781", "#ffffff"


def figura_cobertura(cob: pd.DataFrame, tramo: dict, ruta: Path) -> None:
    etiquetas = cob["periodo"].tolist()
    x = range(len(etiquetas))
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=200)
    fig.patch.set_facecolor(FONDO)
    ax.set_facecolor(FONDO)

    i0, i1 = etiquetas.index(tramo["desde"]), etiquetas.index(tramo["hasta"])
    ax.axvspan(i0 - 0.5, i1 + 0.5, color="#f0efec", zorder=0)
    ax.text((i0 + i1) / 2, cob["incluidas"].max() * 1.04, "Sin código de finalidad\nni estado publicado (R-05)",
            ha="center", va="bottom", fontsize=8, color=TINTA_2)

    ax.bar(x, cob["con_codigo"], width=0.72, color=AZUL, label="Con código de finalidad", zorder=2)
    ax.bar(x, cob["sin_codigo"], width=0.72, bottom=cob["con_codigo"], color=NARANJA,
           label="Sin código de finalidad", zorder=2, edgecolor=FONDO, linewidth=1)

    ax.set_xticks(list(x))
    ax.set_xticklabels([e if e.endswith(("-01", "-07")) else "" for e in etiquetas], fontsize=8, color=MUTED)
    ax.tick_params(axis="y", labelsize=8, colors=MUTED, length=0)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Órdenes ≤ 8 UIT emitidas", fontsize=9, color=TINTA_2)
    ax.set_ylim(0, cob["incluidas"].max() * 1.22)
    ax.grid(axis="y", color="#e6e5e1", linewidth=0.6, zorder=1)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.legend(loc="upper left", frameon=False, fontsize=8, ncol=2, labelcolor=TINTA_2)
    ax.set_title("Órdenes ≤ 8 UIT por mes según presencia del código de finalidad, 2023-2025",
                 fontsize=10, color=TINTA, loc="left")
    fig.tight_layout()
    fig.savefig(ruta, facecolor=FONDO)
    plt.close(fig)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    tramo = ajustes()["tramo_sin_codigo_ni_estado"]
    # Clave fija: el diagnóstico no publica RUC; solo cuenta personas naturales.
    r = construir_ordenes(clave_seudonimo="diagnostico")
    o = r.ordenes
    o["periodo"] = o.anio.astype(str) + "-" + o.mes.astype(str).str.zfill(2)
    inc = o[o.incluida]

    g = inc.groupby("periodo")
    cob = pd.DataFrame({
        "incluidas": g.size(),
        "con_codigo": g.con_codigo.sum(),
        "anuladas": g.estado.apply(lambda s: (s == "anulada").sum()),
        "devengadas": g.estado.apply(lambda s: (s == "devengada").sum()),
        "emitidas": g.estado.apply(lambda s: (s == "emitida").sum()),
        "sin_expediente_siaf": g.expediente_siaf.apply(lambda s: s.isna().sum()),
        "estado_confiable": g.estado_confiable.all(),
    }).reset_index()
    cob["sin_codigo"] = cob.incluidas - cob.con_codigo
    cob["pct_con_codigo"] = (cob.con_codigo / cob.incluidas * 100).round(1)

    vig = inc[inc.estado != "anulada"]
    anual = pd.DataFrame({
        "ordenes_publicadas": o.groupby("anio").size(),
        "derivan_de_seleccion": o.groupby("anio").deviene_seleccion.sum(),
        "ordenes_incluidas": inc.groupby("anio").size(),
        "anuladas_identificables": inc.groupby("anio").estado.apply(lambda s: (s == "anulada").sum()),
        "gasto_incluidas_sin_anuladas_soles": vig.groupby("anio").monto_soles.apply(
            lambda s: float(sum(s, Decimal(0)))).round(2),
        "pct_con_codigo": (inc.groupby("anio").con_codigo.mean() * 100).round(1),
        "pct_persona_natural": (inc.groupby("anio").persona_natural.mean() * 100).round(1),
        "codigos_distintos": inc.groupby("anio").codigo_finalidad.nunique(),
    }).reset_index()

    # Diferencia promedio entre los perfiles mensuales de gasto de 2023 y 2024 (sección 2.2).
    perfil = vig.groupby(["anio", "mes"]).monto_soles.apply(lambda s: float(sum(s, Decimal(0)))).unstack(0)
    perfil = perfil / perfil.sum() * 100
    dif_perfiles = round(float((perfil[2023] - perfil[2024]).abs().mean()), 2)

    resumen = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "commit": commit_actual(),
        "archivos": len(r.manifiesto),
        "archivos_regrabados_en_excel": r.manifiesto.loc[r.manifiesto.regrabado_en_excel, "archivo"].tolist(),
        "ordenes_publicadas": len(o),
        "derivan_de_seleccion": int(o.deviene_seleccion.sum()),
        "ordenes_incluidas": len(inc),
        "ordenes_incluidas_sin_anuladas": len(vig),
        "pct_con_codigo_incluidas": round(float(inc.con_codigo.mean() * 100), 2),
        "codigos_finalidad_distintos_incluidas": int(inc.codigo_finalidad.nunique()),
        "pct_persona_natural_incluidas": round(float(inc.persona_natural.mean() * 100), 2),
        "tramo_sin_codigo_ni_estado": tramo,
        "diferencia_perfiles_mensuales_2023_2024_pp": dif_perfiles,
        "advertencias": r.advertencias,
    }

    r.embudo.to_csv(SALIDA / "embudo_limpieza.csv", index=False, encoding="utf-8")
    cob.to_csv(SALIDA / "cobertura_mensual.csv", index=False, encoding="utf-8")
    anual.to_csv(SALIDA / "resumen_anual.csv", index=False, encoding="utf-8")
    r.manifiesto.to_csv(SALIDA / "manifiesto_archivos.csv", index=False, encoding="utf-8")
    (SALIDA / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    figura_cobertura(cob, tramo, SALIDA / "fig_cobertura_codigo.png")

    print(r.embudo.to_string(index=False))
    print(anual.to_string(index=False))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
