-- Identidades HUB são UUIDs imutáveis, nunca logins/nome de exibição.
CREATE TABLE IF NOT EXISTS vinculos_sso_hub_aeri (
    emissor VARCHAR(40) NOT NULL CHECK (emissor = 'sync-hub'),
    subject UUID NOT NULL,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (emissor, subject)
);

CREATE TABLE IF NOT EXISTS tickets_sso_hub_aeri (
    emissor VARCHAR(40) NOT NULL CHECK (emissor = 'sync-hub'),
    jti UUID NOT NULL,
    expira_em TIMESTAMPTZ NOT NULL,
    consumido_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (emissor, jti)
);
CREATE INDEX IF NOT EXISTS idx_tickets_sso_hub_expira ON tickets_sso_hub_aeri (expira_em);
