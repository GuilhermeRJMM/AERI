-- Proveniência do cadastro legado. NÃO é vínculo de autenticação HUB.
CREATE TABLE IF NOT EXISTS importacoes_usuarios_sync_aeri (
    origem VARCHAR(80) NOT NULL,
    id_sync BIGINT NOT NULL,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario),
    lote UUID NOT NULL,
    origem_fingerprint CHAR(64) NOT NULL,
    importado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (origem,id_sync),
    UNIQUE (origem,usuario)
);
