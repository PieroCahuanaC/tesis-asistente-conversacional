-- Tasa de cifras no sustentadas (Tabla 22): el denominador son las respuestas que contienen cifras.
ALTER TABLE eval.calificacion ADD COLUMN IF NOT EXISTS con_cifras boolean;
CREATE UNIQUE INDEX IF NOT EXISTS calificacion_unica_idx ON eval.calificacion (id_ejecucion, calificador);
