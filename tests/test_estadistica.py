"""Plan de análisis de 3.6 con datos simulados (sin base)."""
import numpy as np
import pandas as pd
import pytest

from asistente.evaluacion import estadistica as E


def simular(p=(0.60, 0.70, 0.90), n=200, semilla=1):
    rng = np.random.default_rng(semilla)
    filas = []
    for i in range(n):
        tipo = f"T{1 + i % 7}"
        facil = rng.random()
        for c, pc in zip(E.CONFIGS, p):
            ok = facil < pc
            filas.append(dict(id_pregunta=f"P{i:03d}", configuracion=c, repeticion=1, tipo=tipo,
                              dificultad=["simple", "agregacion", "varios_pasos"][i % 3], correcta=ok,
                              abstencion=(tipo == "T7" and ok), con_cifras=tipo != "T7",
                              cifras_no_sustentadas=int(rng.random() < 0.05), tiempo_s=rng.lognormal(1 + 0.2 * (c == "C3"), 0.4),
                              tokens=int(rng.normal(4000 + 800 * (c != "C1"), 500)), costo_usd=0.002, respuesta="x"))
    return pd.DataFrame(filas)


def test_wilson_conocido():
    p, lo, hi = E.wilson(160, 200)
    assert p == 0.8 and lo == pytest.approx(0.7389, abs=1e-3) and hi == pytest.approx(0.8495, abs=1e-3)


def test_hipotesis_con_diferencia_clara():
    df = simular()
    m = E.matriz_pareada(df)
    assert E.he1_cochran(m).p_valor < 0.001
    he2, he3 = E.he2_he3(m)
    assert he2.p_ajustado < 0.05 and he2.p_ajustado >= he2.p_valor
    assert E.he4_binomial(df).p_valor < 0.05            # 90 % frente a 0,80


def test_sin_diferencia_no_rechaza():
    df = simular(p=(0.7, 0.7, 0.7))
    assert E.he1_cochran(E.matriz_pareada(df)).p_valor == 1.0
    assert E.he4_binomial(df).decision == "no se rechaza H0"


def test_continuas_y_estabilidad():
    df = simular()
    r = E.comparar_continua(df, "tiempo_s")
    assert r["prueba"].startswith("Friedman") and len(r["pares"]) == 3
    rep = pd.concat([df[df.configuracion == "C3"].assign(repeticion=k) for k in (1, 2, 3)])
    assert E.estabilidad(rep)["coincide_calificacion"] == 1.0


def test_kappa():
    a = pd.Series([1, 1, 0, 0, 1, 0])
    assert E.kappa(a, a) == 1.0
    assert E.kappa(a, 1 - a) < 0


def test_reporte_completo(tmp_path):
    import importlib.util
    from asistente.config import RAIZ
    spec = importlib.util.spec_from_file_location("analizar_lote", RAIZ / "scripts" / "analizar_lote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    texto = mod.analizar(simular(), tmp_path, "simulado")
    assert "HE1" in texto and "HE4" in texto and (tmp_path / "fig_exactitud.png").exists()
