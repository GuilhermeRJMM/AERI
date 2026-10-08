-- Tickets de login do Sync: guarda somente o hash do identificador único.
-- A linha é gravada na mesma transação que cria a sessão AERI.
CREATE TABLE IF NOT EXISTS tickets_sso_sync_aeri (
    jti_hash CHAR(64) PRIMARY KEY,
    expira_em TIMESTAMPTZ NOT NULL,
    consumido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tickets_sso_sync_expira
    ON tickets_sso_sync_aeri (expira_em);
