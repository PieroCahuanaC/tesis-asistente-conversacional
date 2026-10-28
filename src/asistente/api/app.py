"""API del asistente (capa de servicios, sección 4.3; Tabla 15).

Levantar:   uvicorn asistente.api.app:app --port 8000        (documentación en /docs)

La interfaz (Streamlit) solo habla con esta API (RNF-09). Las cifras salen de las mismas piezas que se
evaluaron: el orquestador (C1/C2/C3), las herramientas de C3 y el rol de solo lectura; nada se recalcula aquí.
"""
from __future__ import annotations

import time
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from asistente.api.seguridad import PERMISOS, crear_token, leer_token, puede, verificar_clave
from asistente.config import ajustes, env
from asistente.db.conexion import conectar_admin, conectar_ro
from asistente.herramientas import presupuesto
from asistente.orquestador import CONFIGURACIONES, responder

app = FastAPI(title="Asistente presupuestal Uchumayo", version="1.0",
              description="Consulta presupuestal de contrataciones <= 8 UIT (Municipalidad Distrital de Uchumayo, 2023-2025)")
_bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ dependencias
def db_admin():
    with conectar_admin() as c:
        yield c


def db_ro():
    with conectar_ro() as c:
        yield c


_MODELO = None


def modelo_llm():
    global _MODELO
    if _MODELO is None:
        from asistente.llm.base import crear_modelo
        _MODELO = crear_modelo()
    return _MODELO


def _secreto() -> str:
    s = env("API_SECRETO")
    if len(s) < 32:
        raise RuntimeError("API_SECRETO debe tener al menos 32 caracteres (ver .env.example)")
    return s


class Usuario(BaseModel):
    usuario: str
    perfil: str


def usuario_actual(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> Usuario:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicie sesión", headers={"WWW-Authenticate": "Bearer"})
    carga = leer_token(cred.credentials, _secreto())
    if carga is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o vencida", headers={"WWW-Authenticate": "Bearer"})
    return Usuario(usuario=carga["u"], perfil=carga["p"])


def requiere(funcion: str):
    def _dep(u: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
        if not puede(u.perfil, funcion):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Su perfil ({u.perfil}) no tiene acceso a esta función")
        return u
    return _dep


Admin = Annotated[psycopg.Connection, Depends(db_admin)]
RO = Annotated[psycopg.Connection, Depends(db_ro)]


def _fila(cur, fila) -> dict:
    return {d.name: (float(v) if hasattr(v, "is_finite") else v) for d, v in zip(cur.description, fila)}


def _filas(conn, sql: str, params=()) -> list[dict]:
    cur = conn.execute(sql, params)
    return [_fila(cur, f) for f in cur.fetchall()]


# ------------------------------------------------------------------ autenticación
class Credenciales(BaseModel):
    usuario: str = Field(min_length=3, max_length=40)
    clave: str = Field(min_length=1, max_length=200)


@app.get("/salud")
def salud() -> dict:
    return {"estado": "ok"}


@app.post("/auth/login")
def login(c: Credenciales, admin: Admin) -> dict:
    fila = admin.execute("SELECT nombre, perfil, clave_hash, activo FROM auditoria.usuario WHERE usuario = %s",
                         (c.usuario.lower(),)).fetchone()
    if fila is None or not fila[3] or not verificar_clave(c.clave, fila[2]):
        time.sleep(0.5)                                   # frena intentos repetidos
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o clave incorrectos")
    admin.execute("UPDATE auditoria.usuario SET ultimo_acceso = now() WHERE usuario = %s", (c.usuario.lower(),))
    admin.commit()
    return {"token": crear_token(c.usuario.lower(), fila[1], _secreto()), "usuario": c.usuario.lower(),
            "nombre": fila[0], "perfil": fila[1], "permisos": sorted(f for f, p in PERMISOS.items() if fila[1] in p)}


@app.get("/auth/yo")
def yo(u: Annotated[Usuario, Depends(usuario_actual)]) -> dict:
    return {"usuario": u.usuario, "perfil": u.perfil,
            "permisos": sorted(f for f, p in PERMISOS.items() if u.perfil in p),
            "configuracion_por_defecto": _config_defecto()}


# ------------------------------------------------------------------ asistente (CU-01, CU-03)
def _config_defecto() -> str:
    return ajustes().get("api", {}).get("configuracion_por_defecto", "C3")


class Consulta(BaseModel):
    pregunta: str = Field(min_length=3, max_length=1000)
    configuracion: str | None = Field(default=None, pattern="^C[123]$")
    # Solo administrador: para correr la validación de la etapa 5 a través de la API.
    lote: str | None = None
    id_pregunta: str | None = None
    repeticion: int | None = None


@app.post("/consultas")
def consultar(q: Consulta, u: Annotated[Usuario, Depends(requiere("consultar"))], admin: Admin, ro: RO,
              modelo=Depends(modelo_llm)) -> dict:
    config = q.configuracion or _config_defecto()
    es_admin = puede(u.perfil, "elegir_configuracion")
    if config != _config_defecto() and not es_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador puede elegir la configuración (RF-11)")
    if (q.lote or q.id_pregunta) and not es_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador puede ejecutar preguntas del banco")
    r = responder(q.pregunta, config, modelo, admin, ro, usuario=u.usuario, id_pregunta=q.id_pregunta,
                  repeticion=q.repeticion, lote=q.lote)
    return {"id_ejecucion": r.id_ejecucion, "configuracion": config, "respuesta": r.texto, "abstencion": r.abstencion,
            "pasos": [{"orden": i, "tipo": p.tipo, "nombre": p.nombre, "ok": p.ok, "filas": p.filas}
                      for i, p in enumerate(r.pasos, start=1)],
            "tiempo_s": round(r.tiempo_s, 2), "tokens": r.tokens_entrada + r.tokens_salida,
            "costo_usd": round(r.costo_usd, 6), "error": r.error}


@app.get("/consultas/historial")
def historial(u: Annotated[Usuario, Depends(requiere("consultar"))], admin: Admin,
              limite: int = Query(20, ge=1, le=200)) -> list[dict]:
    return _filas(admin, """SELECT id_ejecucion::text, fecha_hora, configuracion, pregunta, respuesta, abstencion,
                                   tiempo_s FROM auditoria.bitacora WHERE usuario = %s
                            ORDER BY fecha_hora DESC LIMIT %s""", (u.usuario, limite))


@app.get("/consultas/{id_ejecucion}/sustento")
def sustento(id_ejecucion: str, u: Annotated[Usuario, Depends(usuario_actual)], admin: Admin) -> dict:
    """Resultados de SQL o herramientas que respaldan cada cifra de la respuesta (RNF-01)."""
    try:
        cab = _filas(admin, """SELECT id_ejecucion::text, usuario, fecha_hora, configuracion, modelo_version,
                                      modelo_reportado, prompt_sha256, commit_codigo, fecha_corte_datos, pregunta,
                                      respuesta, tiempo_s, tokens_entrada, tokens_salida, costo_usd
                               FROM auditoria.bitacora WHERE id_ejecucion = %s""", (id_ejecucion,))
    except psycopg.errors.InvalidTextRepresentation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución inexistente") from None
    if not cab:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución inexistente")
    if cab[0]["usuario"] != u.usuario and not puede(u.perfil, "bitacora"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puede ver el sustento de sus propias consultas")
    pasos = _filas(admin, """SELECT orden, tipo, nombre, entrada, resultado, filas, ok, error, tiempo_s
                             FROM auditoria.bitacora_paso WHERE id_ejecucion = %s ORDER BY orden""", (id_ejecucion,))
    return cab[0] | {"pasos": pasos}


# ------------------------------------------------------------------ evaluación directa (CU-02, RF-10, RNF-04)
class Requerimiento(BaseModel):
    codigo_finalidad: str = Field(pattern=r"^\d{7}$")
    monto: float = Field(gt=0, lt=1e10)
    periodo: str = Field(pattern=r"^\d{4}-\d{2}$")


@app.get("/metas")
def metas(u: Annotated[Usuario, Depends(requiere("consultar"))], ro: RO,
          texto: str = Query(min_length=3, max_length=100), anio: int | None = None) -> dict:
    return presupuesto.buscar_meta(ro, texto=texto, anio=anio)


@app.post("/requerimientos/evaluar")
def evaluar(req: Requerimiento, u: Annotated[Usuario, Depends(requiere("evaluar_requerimiento"))], ro: RO) -> dict:
    inicio = time.perf_counter()
    r = presupuesto.evaluar_requerimiento(ro, codigo_finalidad=req.codigo_finalidad, monto=req.monto, periodo=req.periodo)
    return r | {"tiempo_s": round(time.perf_counter() - inicio, 3)}


# ------------------------------------------------------------------ panel (CU-04, RF-16, RF-17)
@app.get("/panel/periodos")
def periodos(u: Annotated[Usuario, Depends(requiere("panel"))], ro: RO) -> dict:
    meses = _filas(ro, "SELECT anio, max(mes) AS ultimo_mes FROM datos.v_finalidad_mes GROUP BY anio ORDER BY anio")
    cortes = _filas(ro, "SELECT fuente, max(fecha_corte)::text AS fecha_corte FROM datos.carga GROUP BY fuente")
    return {"anios": meses, "cortes": {c["fuente"]: c["fecha_corte"] for c in cortes}}


@app.get("/panel/ejecucion")
def panel_ejecucion(u: Annotated[Usuario, Depends(requiere("panel"))], ro: RO,
                    anio: int = Query(ge=2023, le=2025), mes: int = Query(ge=1, le=12)) -> dict:
    metas_ = _filas(ro, """SELECT finalidad, nombre_meta, pim, certificado_acum, comprometido_acum, devengado_acum,
                                  saldo, avance_devengado_pct
                           FROM datos.v_finalidad_mes WHERE anio = %s AND mes = %s ORDER BY pim DESC NULLS LAST, finalidad""",
                        (anio, mes))
    tot = {k: round(sum(m[k] or 0 for m in metas_), 2) for k in ("pim", "certificado_acum", "comprometido_acum",
                                                                  "devengado_acum", "saldo")}
    tot["avance_devengado_pct"] = round(100 * tot["devengado_acum"] / tot["pim"], 2) if tot["pim"] else None
    return {"anio": anio, "mes": mes, "totales": tot, "metas": metas_, "fuente": presupuesto.FUENTE_MEF}


@app.get("/panel/meta/{codigo_finalidad}")
def panel_meta(codigo_finalidad: str, u: Annotated[Usuario, Depends(requiere("panel"))], ro: RO,
               anio: int = Query(ge=2023, le=2025)) -> dict:
    if not codigo_finalidad.isdigit() or len(codigo_finalidad) != 7:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El código de finalidad tiene 7 dígitos")
    serie = _filas(ro, """SELECT mes, pim, certificado_mes, certificado_acum, comprometido_acum, devengado_mes,
                                 devengado_acum, saldo, avance_devengado_pct, nombre_meta
                          FROM datos.v_finalidad_mes WHERE anio = %s AND finalidad = %s ORDER BY mes""",
                   (anio, codigo_finalidad))
    if not serie:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La meta no tiene ejecución en ese año")
    return {"codigo_finalidad": codigo_finalidad, "anio": anio, "nombre": serie[0]["nombre_meta"], "meses": serie}


@app.get("/panel/alertas")
def panel_alertas(u: Annotated[Usuario, Depends(requiere("panel"))], ro: RO,
                  periodo: str = Query(pattern=r"^\d{4}-\d{2}$"), umbral: float = Query(80, gt=0, le=100),
                  condicion: str = Query("mayor", pattern="^(mayor|menor)$")) -> dict:
    return presupuesto.alertas_ejecucion(ro, periodo=periodo, umbral_pct=umbral, condicion=condicion)


# ------------------------------------------------------------------ bitácora (RF-19)
@app.get("/bitacora")
def bitacora(u: Annotated[Usuario, Depends(requiere("bitacora"))], admin: Admin,
             limite: int = Query(100, ge=1, le=1000), configuracion: str | None = Query(None, pattern="^C[123]$"),
             usuario: str | None = None, lote: str | None = None) -> list[dict]:
    cond, p = [], []
    for col, val in (("configuracion", configuracion), ("usuario", usuario), ("lote", lote)):
        if val:
            cond.append(f"{col} = %s")
            p.append(val)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    return _filas(admin, f"""SELECT id_ejecucion::text, fecha_hora, usuario, configuracion, lote, id_pregunta, pregunta,
                                    respuesta, abstencion, tiempo_s, tokens_entrada + tokens_salida AS tokens, costo_usd,
                                    reintentos, error
                             FROM auditoria.bitacora {where} ORDER BY fecha_hora DESC LIMIT %s""", (*p, limite))


__all__ = ["app", "CONFIGURACIONES"]
