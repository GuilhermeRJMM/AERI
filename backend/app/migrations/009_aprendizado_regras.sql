CREATE TABLE IF NOT EXISTS regras_aprendizado_aeri (
    id UUID PRIMARY KEY,
    expressao VARCHAR(120) NOT NULL,
    expressao_normalizada VARCHAR(160) NOT NULL,
    categoria VARCHAR(30) NOT NULL CHECK (categoria IN ('ÔNUS', 'RESTRIÇÃO', 'PUBLICIDADE', 'CANCELAMENTO', 'IGNORAR')),
    impacta_resultado BOOLEAN NOT NULL DEFAULT FALSE,
    tipo_onus VARCHAR(80) NOT NULL DEFAULT '',
    justificativa TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE', 'APROVADA', 'REJEITADA')),
    votos INTEGER NOT NULL DEFAULT 1,
    criado_por VARCHAR(40) NOT NULL REFERENCES usuarios_aeri(usuario),
    aprovado_por VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    aprovado_em TIMESTAMPTZ,
    UNIQUE (expressao_normalizada, categoria, tipo_onus)
);

CREATE INDEX IF NOT EXISTS regras_aprendizado_status_idx
    ON regras_aprendizado_aeri (status, atualizado_em DESC);
