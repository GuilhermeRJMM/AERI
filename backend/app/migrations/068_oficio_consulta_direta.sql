CREATE TABLE IF NOT EXISTS conectores_oficio_aeri (
    id UUID PRIMARY KEY,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    cartorio VARCHAR(10) NOT NULL,
    codigo_hash VARCHAR(64) UNIQUE,
    codigo_expira_em TIMESTAMPTZ NOT NULL,
    token_hash VARCHAR(64) UNIQUE,
    expira_em TIMESTAMPTZ NOT NULL,
    revogado_em TIMESTAMPTZ,
    visto_em TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conector_oficio_usuario ON conectores_oficio_aeri(usuario,cartorio);
CREATE TABLE IF NOT EXISTS trabalhos_oficio_aeri (
    id UUID PRIMARY KEY,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    cartorio VARCHAR(10) NOT NULL,
    conector_id UUID REFERENCES conectores_oficio_aeri(id),
    minimo INTEGER NOT NULL CHECK (minimo BETWEEN 1 AND 2000),
    estado VARCHAR(12) NOT NULL CHECK (estado IN ('PENDENTE','LENDO','PRONTO','ERRO')),
    erro VARCHAR(64),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '5 minutes'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trabalho_oficio_ativo
    ON trabalhos_oficio_aeri(usuario,cartorio) WHERE estado IN ('PENDENTE','LENDO');
