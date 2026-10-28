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
| Herramienta C3 `agregar_ordenes` | lista |
| Ingesta de la Consulta Amigable (MEF) y herramientas de saldo/ejecución | pendiente de los datos |
| Configuraciones C1/C2/C3, ejecución por lotes, API, interfaz | S2-S4 |

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
scripts/                  cargar_pte.py, diagnostico_pte.py
reports/                  evidencia generada (tablas y figuras), versionada
tests/                    pytest
data/raw/pte/AAAA/        archivos originales del PTE (no se versionan)
data/manifest_pte.csv     sha256 de cada archivo original (sí se versiona)
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
   python scripts/diagnostico_pte.py
   pytest
   ```

Las pruebas marcadas `db` se omiten si no hay PostgreSQL configurado; las marcadas `datos`, si
faltan los archivos del PTE.

## Reglas que el código fija (y que la tesis debe reflejar)

Ver `docs/decisiones.md`.
