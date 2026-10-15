-- Metadados mínimos; o conteúdo do documento fica em Blob privado e temporário.
CREATE TABLE IF NOT EXISTS rtd_uploads_temporarios_aeri (
    id UUID PRIMARY KEY,
    intimacao_id UUID NOT NULL REFERENCES intimacoes_aeri(id) ON DELETE CASCADE,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    pathname VARCHAR(220) NOT NULL UNIQUE,
    nome_arquivo VARCHAR(120) NOT NULL,
    tamanho_declarado BIGINT NOT NULL CHECK (tamanho_declarado BETWEEN 1 AND 26214400),
    tamanho_verificado BIGINT CHECK (tamanho_verificado IS NULL OR tamanho_verificado BETWEEN 1 AND 26214400),
    estado VARCHAR(20) NOT NULL DEFAULT 'AGUARDANDO_UPLOAD'
        CHECK (estado IN ('AGUARDANDO_UPLOAD', 'PRONTO', 'EXCLUIDO', 'EXPIRADO')),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
    alterado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rtd_uploads_expiracao
    ON rtd_uploads_temporarios_aeri (expira_em)
    WHERE estado IN ('AGUARDANDO_UPLOAD', 'PRONTO');
CREATE INDEX IF NOT EXISTS idx_rtd_uploads_usuario
    ON rtd_uploads_temporarios_aeri (usuario, criado_em DESC);
