"""Interfaz del asistente presupuestal (Streamlit): consulta, evaluación de requerimientos, panel y bitácora.

Levantar:   streamlit run ui/app.py        (la API debe estar en API_URL, por defecto http://localhost:8000)
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from cliente import ErrorApi, llamar

st.set_page_config(page_title="Asistente presupuestal · Uchumayo", page_icon="🏛️", layout="wide")

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre",
         "noviembre", "diciembre"]
PERFIL_TEXTO = {"jefatura": "Jefatura", "area_usuaria": "Área usuaria", "administrador": "Administrador"}
EJEMPLOS = [
    "¿Cuál es el saldo de la meta 0006508 al cierre de junio de 2025?",
    "¿Alcanza el saldo de la meta de parques y jardines para un requerimiento de S/ 20 000 en agosto de 2025?",
    "¿Cuántas órdenes de servicio menores o iguales a 8 UIT se emitieron en julio de 2025 y por qué monto?",
    "¿Qué metas superan el 90 % de ejecución de su PIM al cierre de setiembre de 2025?",
]

st.markdown("""
<style>
  .block-container {max-width: 1100px; padding-top: 2rem;}
  .veredicto {border-left: 6px solid var(--c); padding: .9rem 1.2rem; background: #F6F8F7; border-radius: 4px;}
  .veredicto h3 {margin: 0 0 .2rem 0; color: var(--c);}
  .nota {color: #5B6670; font-size: .85rem;}
</style>""", unsafe_allow_html=True)


def soles(x) -> str:
    if x is None:
        return "—"
    return "S/ " + f"{float(x):,.2f}".replace(",", " ").replace(".", ",")


def millones(x) -> str:
    return "—" if x is None else "S/ " + f"{float(x) / 1e6:,.2f}".replace(".", ",") + " M"


def api(metodo: str, ruta: str, **kw):
    try:
        return llamar(metodo, ruta, token=st.session_state.get("token"), **kw)
    except ErrorApi as e:
        if e.estado == 401 and "token" in st.session_state:
            st.session_state.clear()
            st.warning("Su sesión venció. Ingrese de nuevo.")
            st.rerun()
        st.error(str(e))
        st.stop()


# ------------------------------------------------------------------ ingreso
def pagina_ingreso():
    st.title("Asistente presupuestal")
    st.write("Municipalidad Distrital de Uchumayo · contrataciones menores o iguales a 8 UIT, 2023-2025")
    with st.form("ingreso", border=True):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Clave", type="password")
        if st.form_submit_button("Ingresar", type="primary", use_container_width=True):
            try:
                r = llamar("POST", "/auth/login", json={"usuario": usuario.strip(), "clave": clave})
            except ErrorApi as e:
                st.error(str(e))
            else:
                st.session_state.update(token=r["token"], usuario=r["usuario"], nombre=r["nombre"],
                                        perfil=r["perfil"], permisos=set(r["permisos"]), chat=[])
                st.rerun()


# ------------------------------------------------------------------ asistente
def _mostrar_sustento(id_ejecucion: str):
    s = api("GET", f"/consultas/{id_ejecucion}/sustento")
    st.caption(f"Configuración {s['configuracion']} · modelo {s['modelo_version']} · datos con corte "
               f"{s['fecha_corte_datos']} · registro {s['id_ejecucion'][:8]}")
    if not s["pasos"]:
        st.write("Esta respuesta no consultó datos.")
    for p in s["pasos"]:
        titulo = p["nombre"] if p["tipo"] == "herramienta" else "Consulta SQL"
        st.markdown(f"**{p['orden']}. {titulo}**" + ("" if p["ok"] else " — sin resultado"))
        entrada = p["entrada"] or {}
        if p["tipo"] == "sql" and "consulta" in entrada:
            st.code(entrada["consulta"], language="sql")
        else:
            st.code(json.dumps(entrada, ensure_ascii=False, indent=1), language="json")
        res = p["resultado"]
        if isinstance(res, dict) and isinstance(res.get("filas"), list) and isinstance(res.get("columnas"), list):
            st.dataframe(pd.DataFrame(res["filas"], columns=res["columnas"]), hide_index=True, use_container_width=True)
        elif isinstance(res, dict):
            simples = {k: v for k, v in res.items() if not isinstance(v, (dict, list))}
            st.dataframe(pd.DataFrame({"dato": list(simples), "valor": [str(v) for v in simples.values()]}),
                         hide_index=True, use_container_width=True)
            for k, v in res.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    st.markdown(f"*{k}*")
                    st.dataframe(pd.DataFrame(v), hide_index=True, use_container_width=True)
        else:
            st.json(res, expanded=False)


def _mensaje_asistente(m: dict):
    with st.chat_message("assistant"):
        st.markdown(m["respuesta"])
        detalle = f"{m['tiempo_s']:.1f} s"
        if "configuracion" in st.session_state.get("permisos_vistos", ()):
            detalle += f" · {m['configuracion']} · {m['tokens']} tokens"
        st.caption(detalle)
        if m.get("id_ejecucion") and m.get("pasos"):
            with st.expander("Ver de dónde salen las cifras"):
                _mostrar_sustento(m["id_ejecucion"])


def pagina_asistente():
    st.title("Consultar")
    st.write("Pregunte por saldos, ejecución, órdenes o metas. Cada cifra sale de una consulta registrada; "
             "si los datos no alcanzan para responder, el asistente lo dice.")
    admin = "elegir_configuracion" in st.session_state.permisos
    config = None
    with st.sidebar:
        if admin:
            config = st.radio("Configuración (RF-11)", ["C3", "C2", "C1"], horizontal=True,
                              help="C1: SQL directo · C2: SQL con contexto · C3: herramientas predefinidas")
            st.session_state.permisos_vistos = {"configuracion"}
        st.markdown("**Preguntas de ejemplo**")
        for e in EJEMPLOS:
            if st.button(e, use_container_width=True, key=f"ej-{e[:20]}"):
                st.session_state.pendiente = e
        if st.session_state.chat and st.button("Limpiar conversación", use_container_width=True):
            st.session_state.chat = []
            st.rerun()

    for m in st.session_state.chat:
        if m["rol"] == "usuario":
            st.chat_message("user").markdown(m["texto"])
        else:
            _mensaje_asistente(m)

    pregunta = st.chat_input("Escriba su pregunta, por ejemplo: ¿cuál es el saldo de la meta 0006508 a junio de 2025?")
    pregunta = pregunta or st.session_state.pop("pendiente", None)
    if pregunta:
        st.session_state.chat.append({"rol": "usuario", "texto": pregunta})
        st.chat_message("user").markdown(pregunta)
        with st.spinner("Consultando los datos…"):
            cuerpo = {"pregunta": pregunta} | ({"configuracion": config} if config else {})
            r = api("POST", "/consultas", json=cuerpo)
        m = {"rol": "asistente"} | r
        st.session_state.chat.append(m)
        _mensaje_asistente(m)
    st.markdown('<p class="nota">Las respuestas son orientadoras: no reemplazan la certificación presupuestal '
                'ni el criterio del funcionario.</p>', unsafe_allow_html=True)


# ------------------------------------------------------------------ evaluar requerimiento
def pagina_requerimiento():
    st.title("Evaluar un requerimiento")
    st.write("Indique la meta, el monto y el mes: el sistema compara con el saldo disponible al cierre de ese mes "
             "(PIM menos certificación acumulada).")
    c1, c2 = st.columns([3, 2])
    with c1:
        texto = st.text_input("Meta: código de 7 dígitos o parte del nombre", placeholder="0006508 o parques y jardines")
    with c2:
        anio = st.selectbox("Año", [2025, 2024, 2023])
    codigo = None
    if texto.strip().isdigit() and len(texto.strip()) == 7:
        codigo = texto.strip()
    elif len(texto.strip()) >= 3:
        r = api("GET", "/metas", params={"texto": texto.strip(), "anio": anio})
        opciones = {f"{m['codigo_finalidad']} · {m['nombre']}": m["codigo_finalidad"] for m in r.get("coincidencias", [])}
        if opciones:
            codigo = opciones[st.selectbox("Metas encontradas", list(opciones))]
        else:
            st.info("No hay metas con ese nombre en el año elegido. Pruebe con otra palabra o con el código.")
    c3, c4 = st.columns(2)
    with c3:
        monto = st.number_input("Monto del requerimiento (S/)", min_value=0.0, step=1000.0, format="%.2f")
    with c4:
        mes = st.selectbox("Mes de la evaluación", range(1, 13), format_func=lambda m: MESES[m - 1].capitalize(),
                           index=5)
    if st.button("Evaluar", type="primary", disabled=not (codigo and monto > 0)):
        r = api("POST", "/requerimientos/evaluar",
                json={"codigo_finalidad": codigo, "monto": monto, "periodo": f"{anio}-{mes:02d}"})
        if not r.get("disponible", True):
            st.warning(r.get("motivo", "No hay datos para esa meta y mes."))
            return
        alcanza = r["resultado"] == "alcanza"
        color = "#1F6F5C" if alcanza else "#B4442F"
        st.markdown(f"""<div class="veredicto" style="--c:{color}">
            <h3>{'Alcanza' if alcanza else 'No alcanza'}</h3>
            {'Sobrarían' if alcanza else 'Faltarían'} {soles(abs(r['diferencia']))} después del requerimiento.</div>""",
                    unsafe_allow_html=True)
        k1, k2, k3 = st.columns(3)
        k1.metric("Saldo disponible", soles(r["saldo_disponible"]))
        k2.metric("Requerimiento", soles(monto))
        k3.metric("Diferencia", soles(r["diferencia"]))
        st.caption(f"{r.get('nombre') or codigo} · al cierre de {MESES[mes - 1]} de {anio} · "
                   f"{r['fuente']} (corte {r['fecha_corte']}) · {r['tiempo_s']:.2f} s")
        st.markdown(f'<p class="nota">{r["nota"]}</p>', unsafe_allow_html=True)


# ------------------------------------------------------------------ panel
def pagina_panel():
    st.title("Ejecución por meta")
    per = api("GET", "/panel/periodos")
    anios = [a["anio"] for a in per["anios"]]
    c1, c2, c3, c4 = st.columns([1, 1, 1.4, 1.2])
    anio = c1.selectbox("Año", sorted(anios, reverse=True))
    ultimo = next(a["ultimo_mes"] for a in per["anios"] if a["anio"] == anio)
    mes = c2.selectbox("Al cierre de", range(1, ultimo + 1), index=ultimo - 1, format_func=lambda m: MESES[m - 1].capitalize())
    umbral = c3.slider("Umbral de alerta (% del PIM devengado)", 10, 100, 80, step=5)
    condicion = c4.radio("Alertar metas", ["mayor", "menor"], format_func=lambda c: f"por {'encima' if c == 'mayor' else 'debajo'}",
                         horizontal=True)
    d = api("GET", "/panel/ejecucion", params={"anio": anio, "mes": mes})
    t = d["totales"]
    k = st.columns(4)
    k[0].metric("PIM", millones(t["pim"]), help=soles(t["pim"]))
    k[1].metric("Certificado acumulado", millones(t["certificado_acum"]), help=soles(t["certificado_acum"]))
    k[2].metric("Devengado acumulado", millones(t["devengado_acum"]), help=soles(t["devengado_acum"]))
    k[3].metric("Avance del devengado", f"{t['avance_devengado_pct']:.1f} %".replace(".", ",") if t["avance_devengado_pct"] else "—")

    al = api("GET", "/panel/alertas", params={"periodo": f"{anio}-{mes:02d}", "umbral": umbral, "condicion": condicion})
    en_alerta = {m["codigo_finalidad"] for m in al.get("metas", [])}
    st.subheader(f"{al.get('cantidad', 0)} metas {'sobre' if condicion == 'mayor' else 'bajo'} el {umbral} % de avance")

    df = pd.DataFrame(d["metas"])
    if df.empty:
        st.info("No hay ejecución registrada para ese mes.")
        return
    df["alerta"] = df.finalidad.isin(en_alerta)
    df = df.sort_values(["alerta", "pim"], ascending=[False, False])
    vista = df[["alerta", "finalidad", "nombre_meta", "pim", "devengado_acum", "saldo", "avance_devengado_pct"]]
    sel = st.dataframe(
        vista, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", height=420,
        column_config={
            "alerta": st.column_config.CheckboxColumn("Alerta", width="small"),
            "finalidad": st.column_config.TextColumn("Meta", width="small"),
            "nombre_meta": st.column_config.TextColumn("Nombre", width="medium"),
            "pim": st.column_config.NumberColumn("PIM (S/)", format="localized"),
            "devengado_acum": st.column_config.NumberColumn("Devengado (S/)", format="localized"),
            "saldo": st.column_config.NumberColumn("Saldo sin certificar (S/)", format="localized"),
            "avance_devengado_pct": st.column_config.ProgressColumn("Avance", format="%.1f %%", min_value=0, max_value=100),
        })
    st.caption(f"{d['fuente']} · corte {per['cortes'].get('MEF', '—')} · el PIM es el vigente a la fecha de corte. "
               "Seleccione una fila para ver su evolución mensual.")

    filas = sel.selection.rows if sel and sel.selection else []
    if filas:
        fin = vista.iloc[filas[0]].finalidad
        m = api("GET", f"/panel/meta/{fin}", params={"anio": anio})
        st.subheader(f"{fin} · {m['nombre']}")
        serie = pd.DataFrame(m["meses"]).set_index("mes")[["certificado_acum", "devengado_acum"]]
        serie.columns = ["Certificado acumulado", "Devengado acumulado"]
        serie.index = [MESES[i - 1][:3] for i in serie.index]
        st.line_chart(serie, y_label="Soles", color=["#7FA7C9", "#1F6F5C"])
        st.caption(f"PIM del año: {soles(m['meses'][0]['pim'])}")


# ------------------------------------------------------------------ bitácora
def pagina_bitacora():
    st.title("Bitácora de consultas")
    c1, c2, c3 = st.columns(3)
    config = c1.selectbox("Configuración", ["(todas)", "C1", "C2", "C3"])
    usuario = c2.text_input("Usuario")
    lote = c3.text_input("Lote")
    params = {"limite": 300} | ({"configuracion": config} if config != "(todas)" else {}) \
        | ({"usuario": usuario} if usuario else {}) | ({"lote": lote} if lote else {})
    filas = api("GET", "/bitacora", params=params)
    if not filas:
        st.info("No hay ejecuciones con esos filtros.")
        return
    df = pd.DataFrame(filas)
    st.dataframe(df, hide_index=True, use_container_width=True, height=520)
    st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"bitacora_{date.today()}.csv", mime="text/csv")


# ------------------------------------------------------------------ navegación según el perfil (RF-18)
if "token" not in st.session_state:
    st.navigation([st.Page(pagina_ingreso, title="Ingresar", icon="🔑")], position="hidden").run()
else:
    permisos = st.session_state.permisos
    paginas = [st.Page(pagina_asistente, title="Consultar", icon="💬", default=True),
               st.Page(pagina_requerimiento, title="Evaluar requerimiento", icon="🧾")]
    if "panel" in permisos:
        paginas.append(st.Page(pagina_panel, title="Ejecución por meta", icon="📊"))
    if "bitacora" in permisos:
        paginas.append(st.Page(pagina_bitacora, title="Bitácora", icon="📜"))
    with st.sidebar:
        st.markdown(f"**{st.session_state.nombre}**  \n{PERFIL_TEXTO[st.session_state.perfil]}")
        if st.button("Cerrar sesión"):
            st.session_state.clear()
            st.rerun()
    st.navigation(paginas).run()
