-- Reintentos ante el proveedor (límite de solicitudes, demoras): el tiempo de respuesta total los
-- incluye; el tiempo perdido se guarda aparte para informar también el tiempo neto del asistente.
ALTER TABLE auditoria.bitacora ADD COLUMN IF NOT EXISTS reintentos smallint NOT NULL DEFAULT 0;
ALTER TABLE auditoria.bitacora ADD COLUMN IF NOT EXISTS tiempo_perdido_s numeric(10,3) NOT NULL DEFAULT 0;
