-- Base de datos integrada (sección 4.3.3). Idempotente: se puede ejecutar varias veces.
-- Esquemas separados para que el rol de solo lectura del asistente vea SOLO los datos,
-- nunca el banco de preguntas ni sus respuestas de referencia (evita fuga en C1/C2).
--   datos      -> lo que consulta el asistente (fichas 1 y 2)
--   eval       -> banco de preguntas y calificación (ficha 3)
--   auditoria  -> bitácora del sistema (ficha 4)

CREATE SCHEMA IF NOT EXISTS datos;
CREATE SCHEMA IF NOT EXISTS eval;
CREATE SCHEMA IF NOT EXISTS auditoria;

CREATE TABLE IF NOT EXISTS auditoria.migracion (
    nombre    text PRIMARY KEY,
    aplicada  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- datos
CREATE TABLE IF NOT EXISTS datos.carga (
    id_carga        serial PRIMARY KEY,
    fuente          text NOT NULL CHECK (fuente IN ('PTE', 'MEF')),
    fecha_carga     timestamptz NOT NULL DEFAULT now(),
    fecha_corte     date,
    archivos        jsonb NOT NULL,            -- manifiesto: nombre, sha256, filas
    filas           integer NOT NULL,
    commit_codigo   text NOT NULL
);
COMMENT ON TABLE datos.carga IS 'Cada carga de datos: fuente, fecha de corte y huella de los archivos de origen';

CREATE TABLE IF NOT EXISTS datos.uit (
    anio            smallint PRIMARY KEY,
    valor           numeric(10,2) NOT NULL,
    tope_8_uit      numeric(12,2) GENERATED ALWAYS AS (8 * valor) STORED
);
COMMENT ON TABLE datos.uit IS 'Valor anual de la UIT en soles y tope de 8 UIT';

CREATE TABLE IF NOT EXISTS datos.finalidad (
    codigo_finalidad char(7) PRIMARY KEY,
    nombre_pte       text,                     -- tal como aparece en las órdenes (puede traer «¿»)
    nombre_mef       text,                     -- nombre limpio de la Consulta Amigable
    tipo_gasto       text CHECK (tipo_gasto IN ('corriente', 'inversion')),
    en_mef           boolean                   -- NULL hasta cruzar con la Consulta Amigable
);
COMMENT ON TABLE datos.finalidad IS 'Catálogo de finalidades (metas) presupuestales: código de 7 dígitos y nombre';

CREATE TABLE IF NOT EXISTS datos.orden (
    id_registro        text PRIMARY KEY,       -- AAAA-OC-NNNNN / AAAA-OS-NNNNN
    tipo_orden         text NOT NULL CHECK (tipo_orden IN ('O/C', 'O/S')),
    numero_orden       integer NOT NULL,
    tipo_contratacion  text CHECK (tipo_contratacion IN ('hasta_8_uit', 'deviene_seleccion')),
    codigo_finalidad   char(7) REFERENCES datos.finalidad,
    nombre_finalidad_pte text,
    con_codigo         boolean NOT NULL,
    tipo_gasto         text CHECK (tipo_gasto IN ('corriente', 'inversion')),
    expediente_siaf    text,
    fecha_emision      date NOT NULL,
    fecha_compromiso   date,
    estado             text NOT NULL CHECK (estado IN ('emitida', 'comprometida', 'devengada', 'anulada')),
    monto_soles        numeric(14,4) NOT NULL CHECK (monto_soles >= 0),
    ruc_proveedor      text NOT NULL,          -- seudónimo PN-xxxx si es persona natural
    persona_natural    boolean NOT NULL,
    razon_social       text,                   -- NULL para personas naturales (Ley 29733)
    monto_uit          numeric(12,4) NOT NULL,
    anio               smallint NOT NULL REFERENCES datos.uit,
    mes                smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
    deviene_seleccion  boolean NOT NULL,
    supera_8_uit       boolean NOT NULL,
    incluida           boolean NOT NULL,       -- <= 8 UIT y no deriva de procedimiento de selección
    estado_confiable   boolean NOT NULL,       -- FALSE en ago-2024 a mar-2025 (R-05)
    archivo_origen     text NOT NULL,
    fila_origen        integer NOT NULL,
    id_carga           integer NOT NULL REFERENCES datos.carga,
    UNIQUE (tipo_orden, numero_orden, anio)
);
CREATE INDEX IF NOT EXISTS orden_periodo_idx ON datos.orden (anio, mes);
CREATE INDEX IF NOT EXISTS orden_finalidad_idx ON datos.orden (codigo_finalidad, anio, mes);
COMMENT ON TABLE datos.orden IS 'Órdenes de compra (O/C) y de servicio (O/S) publicadas en el Portal de Transparencia Estándar, 2023-2025';
COMMENT ON COLUMN datos.orden.incluida IS 'TRUE si la orden es <= 8 UIT y no deriva de un procedimiento de selección';
COMMENT ON COLUMN datos.orden.estado_confiable IS 'FALSE entre ago-2024 y mar-2025: el portal no publica el estado real ni el código de finalidad';
COMMENT ON COLUMN datos.orden.monto_soles IS 'Monto de la orden en soles; las anuladas no cuentan como gasto';

-- Ficha 2 (datos.ejecucion_presupuestal) se crea en db/sql/migraciones/001_ejecucion_v2.sql

-- ---------------------------------------------------------------- eval
CREATE TABLE IF NOT EXISTS eval.pregunta (
    id_pregunta       text PRIMARY KEY,
    conjunto          text NOT NULL CHECK (conjunto IN ('desarrollo', 'prueba')),
    tipo_consulta     text NOT NULL CHECK (tipo_consulta IN ('T1','T2','T3','T4','T5','T6','T7')),
    dificultad        text NOT NULL CHECK (dificultad IN ('simple', 'agregacion', 'varios_pasos')),
    texto             text NOT NULL,
    sql_referencia_1  text,                   -- integrante 1
    sql_referencia_2  text,                   -- integrante 2 (cálculo independiente)
    valor_referencia  jsonb,                  -- valor conciliado
    criterio          text NOT NULL CHECK (criterio IN ('numerico', 'lista', 'abstencion')),
    sha256_congelado  text                    -- huella del conjunto de prueba al congelarlo
);

-- ---------------------------------------------------------------- auditoria
CREATE TABLE IF NOT EXISTS auditoria.bitacora (
    id_ejecucion      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha_hora        timestamptz NOT NULL DEFAULT now(),
    usuario           text NOT NULL,
    configuracion     text NOT NULL CHECK (configuracion IN ('C1', 'C2', 'C3')),
    proveedor         text NOT NULL,
    modelo_version    text NOT NULL,          -- modelo solicitado
    modelo_reportado  text,                   -- modelo que informa la API
    temperatura       numeric(4,2),
    semilla           bigint,
    prompt_sha256     text NOT NULL,          -- huella de las instrucciones (RNF-11)
    id_pregunta       text REFERENCES eval.pregunta,
    repeticion        smallint,
    pregunta          text NOT NULL,
    respuesta         text,
    abstencion        boolean,
    tiempo_s          numeric(10,3),
    tokens_entrada    integer,
    tokens_salida     integer,
    costo_usd         numeric(12,8),          -- a precio de lista del proveedor
    fecha_corte_datos date,
    id_carga          integer REFERENCES datos.carga,
    commit_codigo     text NOT NULL,
    error             text
);
CREATE INDEX IF NOT EXISTS bitacora_pregunta_idx ON auditoria.bitacora (id_pregunta, configuracion, repeticion);

CREATE TABLE IF NOT EXISTS auditoria.bitacora_paso (
    id            bigserial PRIMARY KEY,
    id_ejecucion  uuid NOT NULL REFERENCES auditoria.bitacora ON DELETE CASCADE,
    orden         smallint NOT NULL,
    tipo          text NOT NULL CHECK (tipo IN ('sql', 'herramienta')),
    nombre        text,                       -- nombre de la herramienta (C3)
    entrada       jsonb NOT NULL,             -- SQL generado o argumentos de la herramienta
    resultado     jsonb,                      -- lo que vio el modelo: sustenta cada cifra (RNF-01)
    filas         integer,
    ok            boolean NOT NULL,
    error         text,
    tiempo_s      numeric(10,3)
);

CREATE TABLE IF NOT EXISTS eval.calificacion (
    id                     bigserial PRIMARY KEY,
    id_ejecucion           uuid NOT NULL REFERENCES auditoria.bitacora,
    calificador            text NOT NULL CHECK (calificador IN ('automatico', 'calificador_1', 'calificador_2')),
    correcta               boolean NOT NULL,
    abstencion             boolean NOT NULL,
    cifras_no_sustentadas  integer NOT NULL DEFAULT 0,
    observacion            text,
    fecha                  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id_ejecucion, calificador)
);
