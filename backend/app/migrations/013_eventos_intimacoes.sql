CREATE TABLE IF NOT EXISTS eventos_intimacao_aeri (
    id BIGSERIAL PRIMARY KEY,
    intimacao_id UUID NOT NULL,
    protocolo VARCHAR(20) NOT NULL,
    tipo VARCHAR(30) NOT NULL CHECK (
        tipo IN ('CRIACAO', 'ALTERACAO', 'CONFERENCIA', 'ANDAMENTO', 'EXCLUSAO')
    ),
    usuario VARCHAR(40) NOT NULL REFERENCES usuarios_aeri(usuario),
    detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS eventos_intimacao_item_idx
    ON eventos_intimacao_aeri (intimacao_id, criado_em DESC);

CREATE INDEX IF NOT EXISTS eventos_intimacao_protocolo_idx
    ON eventos_intimacao_aeri (protocolo, criado_em DESC);
