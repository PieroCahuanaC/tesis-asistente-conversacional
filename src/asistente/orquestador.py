"""Orquestador de las tres configuraciones de acceso a los datos (Tabla 12, RF-11 a RF-15, RF-19).

Las tres configuraciones usan EL MISMO bucle, el mismo modelo, la misma temperatura y el mismo
máximo de pasos; solo cambia la estrategia de acceso a los datos (decisión D18):
  C1  pregunta + esquema (tablas y columnas)                    -> herramienta única ejecutar_sql
  C2  C1 + descripciones, diccionario semántico y ejemplos      -> herramienta única ejecutar_sql
  C3  descripción de las herramientas predefinidas (Tabla 11)   -> 7 herramientas, sin SQL
Cada paso (SQL o herramienta) y su resultado quedan en la bitácora: sustento de cada cifra (RNF-01).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import psycopg

from asistente.bitacora.registro import Ejecucion, Paso, carga_vigente, huella, registrar
from asistente.config import RAIZ, ajustes
from asistente.herramientas import registro as herramientas
from asistente.llm.base import ModeloLenguaje, costo_usd
from asistente.sql_guard.ejecutor import ejecutar

CONFIGURACIONES = ("C1", "C2", "C3")
MARCA_ABSTENCION = "[ABSTENCIÓN]"
DIR_PROMPTS = RAIZ / "prompts"

ESQUEMA_SQL = {
    "type": "function",
    "function": {
        "name": "ejecutar_sql",
        "description": "Ejecuta una consulta SQL de solo lectura (un único SELECT, PostgreSQL) sobre el esquema "
                       "datos y devuelve columnas y filas (máximo 500).",
        "parameters": {"type": "object",
                       "properties": {"consulta": {"type": "string", "description": "Consulta SELECT"}},
                       "required": ["consulta"], "additionalProperties": False},
    },
}


@dataclass
class Respuesta:
    texto: str
    abstencion: bool
    id_ejecucion: str | None
    pasos: list[Paso]
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float
    tiempo_s: float
    error: str | None = None


def _leer_prompt(nombre: str) -> str:
    return (DIR_PROMPTS / nombre).read_text(encoding="utf-8").strip()


def describir_esquema(conn: psycopg.Connection, con_descripciones: bool) -> str:
    """Esquema de las tablas y vistas del esquema datos tal como lo ve el asistente."""
    filas = conn.execute("""
        SELECT c.relname, c.relkind, obj_description(c.oid, 'pg_class'),
               a.attname, format_type(a.atttypid, a.atttypmod), col_description(c.oid, a.attnum)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE n.nspname = 'datos' AND c.relkind IN ('r', 'v')
        ORDER BY c.relname, a.attnum""").fetchall()
    tablas: dict[str, list] = {}
    comentarios: dict[str, str | None] = {}
    for tabla, tipo, com_t, col, tipo_col, com_c in filas:
        tablas.setdefault(tabla, []).append((col, tipo_col, com_c))
        comentarios[tabla] = com_t
    lineas = []
    for tabla, columnas in tablas.items():
        cabecera = f"datos.{tabla}"
        if con_descripciones and comentarios[tabla]:
            cabecera += f"  -- {comentarios[tabla]}"
        lineas.append(cabecera)
        for col, tipo_col, com_c in columnas:
            linea = f"  {col} {tipo_col}"
            if con_descripciones and com_c:
                linea += f"  -- {com_c}"
            lineas.append(linea)
    return "\n".join(lineas)


def construir_contexto(conn_admin: psycopg.Connection, configuracion: str) -> tuple[str, list[dict]]:
    """Devuelve (instrucciones del sistema, herramientas) de la configuración."""
    if configuracion not in CONFIGURACIONES:
        raise ValueError(f"Configuración desconocida: {configuracion}")
    cortes = dict(conn_admin.execute("SELECT fuente, max(fecha_corte)::text FROM datos.carga GROUP BY fuente").fetchall())
    origen = "las herramientas" if configuracion == "C3" else "las consultas SQL"
    comun = _leer_prompt("comun.md").format(origen_cifras=origen, corte_pte=cortes.get("PTE", "s/d"),
                                            corte_mef=cortes.get("MEF", "s/d"))
    if configuracion == "C3":
        return comun + "\n\n" + _leer_prompt("c3.md"), herramientas.esquemas()
    esquema = describir_esquema(conn_admin, con_descripciones=configuracion == "C2")
    if configuracion == "C1":
        especifico = _leer_prompt("c1.md").format(esquema=esquema)
    else:
        especifico = _leer_prompt("c2.md").format(esquema=esquema, ejemplos=_leer_prompt("c2_ejemplos.md"))
    return comun + "\n\n" + especifico, [ESQUEMA_SQL]


def _ejecutar_paso(conn_ro: psycopg.Connection, configuracion: str, nombre: str, argumentos: dict) -> Paso:
    if configuracion == "C3":
        return herramientas.invocar(conn_ro, nombre, argumentos)
    if nombre != "ejecutar_sql" or "consulta" not in argumentos:
        return Paso(tipo="sql", nombre=nombre, entrada=argumentos, ok=False,
                    resultado={"ok": False, "error": "Use la herramienta ejecutar_sql con el parámetro consulta"},
                    error="llamada inválida")
    r = ejecutar(argumentos["consulta"], conn_ro)
    return Paso(tipo="sql", nombre="ejecutar_sql", entrada={"consulta": argumentos["consulta"]},
                resultado=r.como_json(), filas=len(r.filas), ok=r.ok, error=r.error, tiempo_s=r.tiempo_s)


def responder(pregunta: str, configuracion: str, modelo: ModeloLenguaje,
              conn_admin: psycopg.Connection, conn_ro: psycopg.Connection,
              usuario: str = "cli", id_pregunta: str | None = None, repeticion: int | None = None,
              registrar_bitacora: bool = True) -> Respuesta:
    cfg = ajustes()["llm"]
    max_pasos = int(cfg.get("max_pasos", 6))
    sistema, tools = construir_contexto(conn_admin, configuracion)
    huella_prompt = huella(sistema + json.dumps(tools, sort_keys=True, ensure_ascii=False))
    mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": pregunta}]

    pasos: list[Paso] = []
    tok_in = tok_out = 0
    modelo_reportado = None
    texto, error = None, None
    inicio = time.perf_counter()
    try:
        for _ in range(max_pasos + 1):
            r = modelo.generar(mensajes, herramientas=tools)
            tok_in += r.tokens_entrada
            tok_out += r.tokens_salida
            modelo_reportado = r.modelo_reportado or modelo_reportado
            if not r.llamadas:
                texto = (r.texto or "").strip()
                break
            if len(pasos) >= max_pasos:
                error = f"Se alcanzó el máximo de {max_pasos} pasos sin respuesta final"
                break
            mensajes.append(r.mensaje_crudo)
            for llamada in r.llamadas:
                paso = _ejecutar_paso(conn_ro, configuracion, llamada.nombre, llamada.argumentos)
                pasos.append(paso)
                mensajes.append({"role": "tool", "tool_call_id": llamada.id,
                                 "content": json.dumps(paso.resultado, ensure_ascii=False, default=str)})
    except Exception as e:  # error del proveedor u otro: queda en la bitácora
        error = f"{type(e).__name__}: {e}"
    tiempo = time.perf_counter() - inicio

    if not texto:
        texto = f"{MARCA_ABSTENCION} No fue posible obtener una respuesta." if error else ""
    abstencion = texto.startswith(MARCA_ABSTENCION)
    costo = costo_usd(tok_in, tok_out, cfg)

    id_ejecucion = None
    if registrar_bitacora:
        id_carga, corte = carga_vigente(conn_admin)
        id_ejecucion = registrar(conn_admin, Ejecucion(
            usuario=usuario, configuracion=configuracion, proveedor=modelo.proveedor,
            modelo_version=modelo.modelo, modelo_reportado=modelo_reportado, temperatura=modelo.temperatura,
            semilla=modelo.semilla, prompt_sha256=huella_prompt, id_pregunta=id_pregunta, repeticion=repeticion,
            pregunta=pregunta, respuesta=texto, abstencion=abstencion, tiempo_s=round(tiempo, 3),
            tokens_entrada=tok_in, tokens_salida=tok_out, costo_usd=costo, fecha_corte_datos=corte,
            id_carga=id_carga, error=error, pasos=pasos))
    return Respuesta(texto=texto, abstencion=abstencion, id_ejecucion=id_ejecucion, pasos=pasos,
                     tokens_entrada=tok_in, tokens_salida=tok_out, costo_usd=costo, tiempo_s=tiempo, error=error)
