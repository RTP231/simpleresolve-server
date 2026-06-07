-- Ejecutar en el SQL Editor de Supabase

-- ── Tabla principal de usuarios ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                 UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    email              VARCHAR(255) UNIQUE NOT NULL,
    hashed_password    TEXT        NOT NULL,
    captures_remaining INTEGER     NOT NULL DEFAULT 200,
    captures_limite    INTEGER,
    fecha_vencimiento  TIMESTAMPTZ,
    activo             BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migración: añadir columnas a tabla existente (si ya existe la tabla)
ALTER TABLE users ADD COLUMN IF NOT EXISTS captures_limite   INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS fecha_vencimiento TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS activo            BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS users_email_idx ON users(email);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Usar OR REPLACE (PG14+) para no fallar si el trigger ya existe
CREATE OR REPLACE TRIGGER set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ── Configuración del panel admin ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
