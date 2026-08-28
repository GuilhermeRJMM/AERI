CREATE TABLE IF NOT EXISTS livro_protocolos_rodadas_aeri (
    id UUID PRIMARY KEY,
    data_esperada DATE NOT NULL,
    fonte VARCHAR(30) NOT NULL,
    regras_hash CHAR(64) NOT NULL,
    resultado JSONB NOT NULL,
    resumo JSONB NOT NULL,
    criado_por VARCHAR(80) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_livro_protocolos_rodadas_data
    ON livro_protocolos_rodadas_aeri (data_esperada, criado_em DESC);

ALTER TABLE livro_protocolos_excecoes_natureza_aeri
    ADD COLUMN IF NOT EXISTS ativa BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS justificativa VARCHAR(500),
    ADD COLUMN IF NOT EXISTS vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS vigencia_fim DATE,
    ADD COLUMN IF NOT EXISTS atualizado_por VARCHAR(80) REFERENCES usuarios_aeri(usuario),
    ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS livro_protocolos_excecoes_eventos_aeri (
    id BIGSERIAL PRIMARY KEY,
    excecao_id UUID NOT NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('CRIACAO', 'DESATIVACAO', 'REATIVACAO')),
    usuario VARCHAR(80) REFERENCES usuarios_aeri(usuario),
    detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_livro_excecoes_eventos
    ON livro_protocolos_excecoes_eventos_aeri (excecao_id, criado_em DESC);
