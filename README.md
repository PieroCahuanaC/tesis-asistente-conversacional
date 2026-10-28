# Asistente presupuestal Uchumayo

Código de la tesis *Optimización de la consulta presupuestal en las contrataciones menores o
iguales a 8 UIT mediante un asistente conversacional basado en modelos de lenguaje de gran escala
en la Municipalidad de Uchumayo, 2023-2025* (Arenas Ichocan y Cahuana Cabrera, UCSM).

## Estado (sprint S1)

| Componente | Estado |
|---|---|
| Ingesta del PTE (36 archivos, 2023-2025) | listo, con pruebas |
| Diagnóstico de datos para el Cap. IV | listo (`reports/diagnostico_pte/`) |
| Base PostgreSQL: esquemas `datos`/`eval`/`auditoria`, rol `asistente_ro` | listo |
| Validador SQL de solo lectura (RNF-02) | listo, 100 % de ataques bloqueados |
| Interfaz LLM independiente del proveedor + adaptador Groq/OpenAI | listo (sin llamadas reales aún) |
| Bitácora (Ficha 4) | lista |
| Ingesta de la Consulta Amigable (MEF) y vista de saldo por finalidad y mes | listo |
| Las 7 herramientas de C3 (Tabla 11), contrastadas con cálculos independientes | listas |
| Orquestador C1/C2/C3 (mismo bucle, prompts versionados en `prompts/`) y comando `scripts/preguntar.py` | listo |
| Banco de 230 preguntas y solucionario por doble cálculo A (SQL) / B (Python sobre archivos): 207/207 coinciden | listo: falta la verificación manual del 20 % y el juicio de expertos |
| Ejecución por lotes (`cargar_banco.py`, `ejecutar_lote.py`): piloto, principal y estabilidad, reanudable | listo |
| Calificación automática (`calificar_lote.py`) y estadística de 3.6 con figuras (`analizar_lote.py`) | listo; falta calibrar con el piloto |
| API (FastAPI), interfaz Streamlit (consulta, evaluación, panel, bitácora), usuarios por perfil y Docker (S4) | listo |

## Estructura

```
config/settings.yaml      parámetros del estudio (UIT, tramo R-05, modelo, precios)
db/sql/                   esquema y permisos de PostgreSQL
src/asistente/
  ingesta/                limpieza y lectura del PTE (Ficha 1)
  db/                     conexión, migración y carga
  sql_guard/              validador y ejecutor SQL de solo lectura (C1/C2)
  llm/                    interfaz del modelo de lenguaje y adaptadores
  bitacora/               registro de cada ejecución (Ficha 4)
  herramientas/           herramientas de consulta de C3 (Tabla 11)
  api/                    API FastAPI: autenticación por perfil, consultas, panel, bitácora
  evaluacion/             criterio de corrección, familias de preguntas y doble cálculo del solucionario
ui/                       interfaz Streamlit (solo habla con la API)
prompts/                  instrucciones de cada configuración (versionadas; su sha256 va a la bitácora)
scripts/                  cargar_pte.py, filtrar_mef.py, cargar_mef.py, diagnostico_pte.py, preguntar.py,
                          generar_banco.py, calcular_referencias.py,
                          cargar_banco.py, generar_ejemplos_c2.py, ejecutar_lote.py
eval/banco/               banco de preguntas (Excel) con el solucionario
reports/                  evidencia generada (tablas y figuras), versionada
tests/                    pytest
data/raw/pte/AAAA/        archivos originales del PTE (no se versionan)
data/manifest_pte.csv     sha256 de cada archivo original del PTE (sí se versiona)
data/raw/mef/             CSV del MEF y sus versiones filtradas (no se versionan)
data/manifest_mef.csv     sha256 de cada CSV original del MEF (sí se versiona)
```

## Instalación (Windows)

1. **Python 3.11 o superior** (probado con 3.13).
2. **PostgreSQL 16**, de una de estas dos formas:
   - Docker Desktop: `docker compose up -d db`
   - Instalador nativo de PostgreSQL 16 (puerto 5432, usuario `postgres`).
3. Entorno e dependencias:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.lock
   pip install -e .
   ```
4. Credenciales: copiar `.env.example` a `.env` y completar. La clave de seudonimización se
   genera una sola vez y **debe ser la misma para los dos integrantes**:
   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
5. Base de datos y carga:
   ```powershell
   python -m asistente.db.migrar
   python scripts/cargar_pte.py --fecha-corte AAAA-MM-DD   # fecha en que se descargaron los .xls
   python scripts/filtrar_mef.py                          # una vez: reduce los CSV nacionales del MEF a Uchumayo
   python scripts/cargar_mef.py --fecha-corte AAAA-MM-DD   # fecha de descarga de los CSV del MEF
   python scripts/diagnostico_pte.py
   pytest
   ```

## Usar el asistente (S4)

Sin Docker (dos terminales, con el venv activo y `API_SECRETO` en el `.env`):
```powershell
python scripts/crear_usuario.py --usuario pcahuana --nombre "Piero Cahuana" --perfil administrador
uvicorn asistente.api.app:app --port 8000          # terminal 1 (documentación en http://localhost:8000/docs)
streamlit run ui/app.py                            # terminal 2 -> http://localhost:8501
```

Con Docker (RNF-10), en un equipo nuevo:
```powershell
docker compose up -d --build
docker compose run --rm api python scripts/cargar_pte.py --fecha-corte AAAA-MM-DD
docker compose run --rm api python scripts/cargar_mef.py --fecha-corte AAAA-MM-DD
docker compose run --rm api python scripts/crear_usuario.py --usuario admin --nombre "Administrador" --perfil administrador
```

Perfiles (RF-18): **jefatura** (consulta, evaluación y panel), **area_usuaria** (consulta y evaluación),
**administrador** (todo, además elegir C1/C2/C3 y ver la bitácora completa).

Las pruebas marcadas `db` se omiten si no hay PostgreSQL configurado; las marcadas `datos`, si
faltan los archivos del PTE.

## Reglas que el código fija (y que la tesis debe reflejar)

Ver `docs/decisiones.md`.
