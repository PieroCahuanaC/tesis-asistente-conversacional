"""Calificación automática: formatos de cifras en español y reglas por familia."""
import pytest

from asistente.evaluacion.calificar import calificar, cifras


@pytest.mark.parametrize("texto, valor", [
    ("S/ 1 452 526,89", 1452526.89), ("S/ 1.452.526,89", 1452526.89), ("S/ 1,452,526.89", 1452526.89),
    ("S/ 1452526.89", 1452526.89), ("75,43 %", 75.43), ("−10 600,00", -10600.0), ("266 órdenes", 266),
    ("S/ 41.200", 41200), ("S/ 39 600,00", 39600),
])
def test_cifras_en_formatos_peruanos(texto, valor):
    assert any(valor in v for v in cifras(texto))


def test_fechas_no_son_cifras():
    assert cifras("Fuente: Consulta Amigable (corte 2026-10-28).") == []


def _c(resp, fam, ref, criterio="numerico", pregunta="¿?", pasos=None):
    return calificar(resp, pregunta, fam, criterio, ref, pasos or [])


def test_monto_con_tolerancia_y_abstencion_indebida():
    assert _c("El saldo es S/ 88 726,40.", "saldo", [[88726.0]]).correcta
    assert not _c("El saldo es S/ 90 000,00.", "saldo", [[88726.0]]).correcta
    r = _c("[ABSTENCIÓN] No tengo datos.", "saldo", [[88726.0]])
    assert not r.correcta and r.abstencion


def test_t7_correcta_solo_si_se_abstiene():
    assert _c("[ABSTENCIÓN] 2022 está fuera del periodo.", "no_respondible", "NO RESPONDIBLE", "abstencion").correcta
    assert not _c("En 2022 el saldo fue S/ 10,00.", "no_respondible", "NO RESPONDIBLE", "abstencion").correcta


def test_conteo_exacto_y_monto():
    ref = [[270, 1706334.48]]
    assert _c("Se emitieron 270 órdenes por S/ 1 706 334,48.", "ordenes_periodo", ref).correcta
    assert not _c("Se emitieron 268 órdenes por S/ 1 706 334,48.", "ordenes_periodo", ref).correcta


def test_lista_sin_orden():
    ref = [["0006508", 1.0], ["0042405", 2.0], ["0000888", 3.0]]
    assert _c("Las metas son 0000888, 0006508 y 0042405.", "top_ordenes", ref, "lista").correcta
    assert not _c("Las metas son 0000888 y 0006508.", "top_ordenes", ref, "lista").correcta


def test_alcanza_y_no_alcanza():
    ref_no = [[53900.0, -10600.0, "no alcanza"]]
    assert _c("No alcanza: el saldo es S/ 53 900,00 y faltarían S/ 10 600,00.", "alcanza", ref_no).correcta
    assert not _c("Sí alcanza, el saldo es S/ 53 900,00.", "alcanza", ref_no).correcta
    ref_si = [[161487.0, 66487.0, "alcanza"]]
    assert _c("Sí le alcanza: saldo S/ 161 487,00; sobrarían S/ 66 487,00.", "alcanza", ref_si).correcta


def test_mes_trimestre_y_porcentaje():
    assert _c("El trimestre con más devengado fue el tercer trimestre, con S/ 25 724 256,64.", "trim_max_dev",
              [[3, 25724256.64]]).correcta
    assert _c("Fue en marzo, con 312 órdenes.", "mes_max_ordenes", [[3, 312]]).correcta
    assert _c("Sí, su avance es 75,43 %, supera el 60 %.", "avance_meta", [[75.43, "sí"]]).correcta
    assert not _c("No supera el umbral: 75,43 %.", "avance_meta", [[75.43, "sí"]]).correcta


def test_cero_en_palabras():
    assert _c("En ese periodo no se registró devengado en la meta.", "dev_rango", [[0.0]]).correcta


def test_cifras_no_sustentadas():
    pasos = [{"ok": True, "filas": [[88726]]}]
    r = _c("El saldo es S/ 88 726,00. Además tiene S/ 5 000 en trámite.", "saldo", [[88726.0]], pasos=pasos)
    assert r.correcta and r.cifras_no_sustentadas == 1
    r = _c("Alcanza: saldo S/ 161 487,00, sobran S/ 66 487,00.", "alcanza", [[161487.0, 66487.0, "alcanza"]],
           pregunta="¿Alcanza para S/ 95 000?", pasos=[{"saldo": 161487.0}])
    assert r.cifras_no_sustentadas == 0                      # 66 487 = 161 487 − 95 000
