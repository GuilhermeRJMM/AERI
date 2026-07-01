CREATE TABLE IF NOT EXISTS usuarios_aeri (
    usuario VARCHAR(80) PRIMARY KEY,
    senha_hash TEXT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intimacoes_aeri (
    id UUID PRIMARY KEY,
    protocolo VARCHAR(10) NOT NULL UNIQUE,
    credor VARCHAR(160) NOT NULL,
    devedor VARCHAR(160) NOT NULL,
    ultimo_andamento DATE NOT NULL,
    ultima_conferencia DATE,
    historico JSONB NOT NULL DEFAULT '[]'::jsonb,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
