-- Ejecución por lotes (etapas 3 y 5 de 3.5.4): cada ejecución del banco pertenece a un lote
-- (piloto, principal, estabilidad) y el lote guarda la huella del banco y del modelo con que se corrió.
CREATE TABLE IF NOT EXISTS eval.lote (
    nombre          text PRIMARY KEY,
    descripcion     text,
    conjunto        text NOT NULL CHECK (conjunto IN ('desarrollo', 'prueba')),
    configuraciones text[] NOT NULL,
    repeticiones    smallint NOT NULL DEFAULT 1,
    banco_sha256    text NOT NULL,          -- huella de preguntas y referencias usadas
    modelo          text NOT NULL,
    proveedor       text NOT NULL,
    semilla         bigint,
    inicio          timestamptz NOT NULL DEFAULT now(),
    fin             timestamptz,
    commit_inicio   text NOT NULL
);

ALTER TABLE auditoria.bitacora ADD COLUMN IF NOT EXISTS lote text REFERENCES eval.lote;
CREATE INDEX IF NOT EXISTS bitacora_lote_idx ON auditoria.bitacora (lote, id_pregunta, configuracion, repeticion);

ALTER TABLE eval.pregunta ADD COLUMN IF NOT EXISTS familia text;
ALTER TABLE eval.pregunta ADD COLUMN IF NOT EXISTS interpretacion text;
