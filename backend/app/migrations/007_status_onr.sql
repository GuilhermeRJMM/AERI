CREATE TABLE IF NOT EXISTS status_onr_aeri (
    chave VARCHAR(120) PRIMARY KEY,
    nome VARCHAR(180) NOT NULL,
    status VARCHAR(30) NOT NULL,
    origem VARCHAR(20) NOT NULL,
    detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
    atualizado_origem_em TIMESTAMPTZ,
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS eventos_onr_aeri (
    id BIGSERIAL PRIMARY KEY,
    hash_evento CHAR(64) NOT NULL UNIQUE,
    tipo VARCHAR(30) NOT NULL,
    referencia VARCHAR(120),
    status VARCHAR(30),
    resumo VARCHAR(300),
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eventos_onr_recebido
    ON eventos_onr_aeri (recebido_em DESC);
