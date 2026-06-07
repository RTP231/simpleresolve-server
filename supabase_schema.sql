-- Ejecutar en el SQL Editor de Supabase
CREATE TABLE IF NOT EXISTS users (
    id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    email            VARCHAR(255) UNIQUE NOT NULL,
    hashed_password  TEXT        NOT NULL,
    captures_remaining INTEGER   NOT NULL DEFAULT 200,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS users_email_idx ON users(email);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
