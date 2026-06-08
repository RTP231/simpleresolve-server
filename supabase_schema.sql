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

-- ── Email de bienvenida (tracking) y creación ────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent_at   TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_opened_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_resend_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by_ip     TEXT;

-- ── Historial de recargas de capturas ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS capture_reloads (
    id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id              UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount               INTEGER     NOT NULL,
    captures_total_after INTEGER     NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS capture_reloads_user_idx ON capture_reloads(user_id);

-- ── Historial de emails enviados ──────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_email_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS email_logs (
    id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        TEXT        NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      TEXT        NOT NULL DEFAULT 'sent',
    metadata    JSONB,
    brevo_id    TEXT
);

CREATE INDEX IF NOT EXISTS email_logs_user_idx ON email_logs(user_id);
