CREATE TABLE IF NOT EXISTS divergencias_analise_aeri (
    id UUID PRIMARY KEY,
    numero_matricula VARCHAR(20) NOT NULL,
    motor_versao VARCHAR(30) NOT NULL,
    resultado_hash CHAR(64) NOT NULL,
    avaliacao VARCHAR(20) NOT NULL CHECK (avaliacao IN ('CORRETO', 'REVISAR')),
    dominios JSONB NOT NULL DEFAULT '[]'::jsonb,
    comentario VARCHAR(1000) NOT NULL DEFAULT '',
    resumo JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE'
        CHECK (status IN ('PENDENTE', 'RESOLVIDA', 'ARQUIVADA')),
    criado_por VARCHAR(40) NOT NULL REFERENCES usuarios_aeri(usuario),
    revisado_por VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    resolucao VARCHAR(1000) NOT NULL DEFAULT '',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revisado_em TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS divergencias_analise_status_idx
    ON divergencias_analise_aeri (status, criado_em DESC);

CREATE INDEX IF NOT EXISTS divergencias_analise_matricula_idx
    ON divergencias_analise_aeri (numero_matricula, criado_em DESC);
