CREATE TABLE IF NOT EXISTS preparacoes_intimacao_aeri (
    id UUID PRIMARY KEY,
    intimacao_id UUID NOT NULL REFERENCES intimacoes_aeri(id) ON DELETE CASCADE,
    usuario VARCHAR(120) NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('PENDENTE','LENDO','PRONTO','ERRO')),
    dados_cifrados TEXT,
    erro VARCHAR(500),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '1 day'
);
CREATE INDEX IF NOT EXISTS preparacoes_intimacao_fila ON preparacoes_intimacao_aeri(estado, criado_em);
CREATE UNIQUE INDEX IF NOT EXISTS preparacoes_intimacao_pendente
    ON preparacoes_intimacao_aeri(intimacao_id, usuario) WHERE estado IN ('PENDENTE','LENDO');
