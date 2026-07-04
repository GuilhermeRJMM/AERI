CREATE TABLE IF NOT EXISTS sessoes_aeri (
    id UUID PRIMARY KEY,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    csrf_hash CHAR(64) NOT NULL,
    ip VARCHAR(64),
    user_agent VARCHAR(300),
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_acesso TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL,
    revogada_em TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessoes_token_ativo
    ON sessoes_aeri (token_hash, expira_em) WHERE revogada_em IS NULL;

CREATE TABLE IF NOT EXISTS tentativas_login_aeri (
    id BIGSERIAL PRIMARY KEY,
    usuario VARCHAR(80) NOT NULL,
    ip VARCHAR(64) NOT NULL,
    sucesso BOOLEAN NOT NULL DEFAULT FALSE,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tentativas_login_recente
    ON tentativas_login_aeri (ip, usuario, criada_em DESC);

CREATE TABLE IF NOT EXISTS auditoria_aeri (
    id BIGSERIAL PRIMARY KEY,
    usuario VARCHAR(80),
    acao VARCHAR(80) NOT NULL,
    recurso VARCHAR(120),
    resultado VARCHAR(30) NOT NULL,
    ip VARCHAR(64),
    detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auditoria_criada_em ON auditoria_aeri (criada_em DESC);
