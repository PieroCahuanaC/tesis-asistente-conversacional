-- Usuarios del asistente y su perfil (RF-18, RNF-05). En el esquema auditoria: invisible para asistente_ro.
CREATE TABLE IF NOT EXISTS auditoria.usuario (
    usuario      text PRIMARY KEY CHECK (usuario ~ '^[a-z0-9._-]{3,40}$'),
    nombre       text NOT NULL,
    perfil       text NOT NULL CHECK (perfil IN ('jefatura', 'area_usuaria', 'administrador')),
    clave_hash   text NOT NULL,              -- pbkdf2_sha256$iteraciones$sal$hash
    activo       boolean NOT NULL DEFAULT true,
    creado       timestamptz NOT NULL DEFAULT now(),
    ultimo_acceso timestamptz
);
