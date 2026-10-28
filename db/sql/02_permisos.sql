-- Permisos del rol de solo lectura (RF-12, RNF-02). El rol se crea en asistente/db/migrar.py
-- con la contraseña de .env. Este archivo es idempotente.
-- Defensa en profundidad: (1) el rol solo tiene SELECT sobre el esquema datos,
-- (2) toda transacción del rol es de solo lectura por defecto, (3) tiempo máximo por sentencia,
-- (4) además, el validador sintáctico (asistente/sql_guard) rechaza todo lo que no sea un SELECT.

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA datos, eval, auditoria FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA eval, auditoria FROM asistente_ro;

GRANT USAGE ON SCHEMA datos TO asistente_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA datos TO asistente_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA datos GRANT SELECT ON TABLES TO asistente_ro;

ALTER ROLE asistente_ro SET default_transaction_read_only = on;
ALTER ROLE asistente_ro SET statement_timeout = '5s';
ALTER ROLE asistente_ro SET search_path = datos;
