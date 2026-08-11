CREATE TABLE IF NOT EXISTS auditorias_matriculas_aeri (
    matricula_numero INTEGER PRIMARY KEY REFERENCES matriculas_busca_aeri(numero) ON DELETE CASCADE,
    resultado_hash CHAR(64),
    auditoria_hash CHAR(64) NOT NULL,
    estado VARCHAR(32) NOT NULL,
    prioridade VARCHAR(24) NOT NULL,
    confianca_onus VARCHAR(16) NOT NULL,
    confianca_cadeia VARCHAR(16) NOT NULL,
    confianca_imovel VARCHAR(16) NOT NULL,
    veredito_onus VARCHAR(16) NOT NULL,
    veredito_cadeia VARCHAR(16) NOT NULL,
    veredito_imovel VARCHAR(16) NOT NULL,
    alertas JSONB NOT NULL DEFAULT '[]'::jsonb,
    metricas JSONB NOT NULL DEFAULT '{}'::jsonb,
    complemento_status VARCHAR(20) NOT NULL DEFAULT 'NAO_NECESSARIA',
    complemento_modelo VARCHAR(80) NOT NULL DEFAULT '',
    complemento_diagnostico JSONB,
    complemento_unidades_entrada INTEGER NOT NULL DEFAULT 0,
    complemento_unidades_saida INTEGER NOT NULL DEFAULT 0,
    complemento_tentativas SMALLINT NOT NULL DEFAULT 0,
    complemento_erro VARCHAR(240) NOT NULL DEFAULT '',
    complemento_em TIMESTAMPTZ,
    analisado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT auditoria_complemento_status_valido CHECK (
        complemento_status IN ('NAO_NECESSARIA','PENDENTE','PROCESSANDO','CONCLUIDA','FALHA','DESATIVADA')
    )
);

CREATE INDEX IF NOT EXISTS idx_auditorias_matriculas_prioridade
    ON auditorias_matriculas_aeri (prioridade, matricula_numero);
CREATE INDEX IF NOT EXISTS idx_auditorias_matriculas_estado
    ON auditorias_matriculas_aeri (estado, matricula_numero);
CREATE INDEX IF NOT EXISTS idx_auditorias_matriculas_complemento
    ON auditorias_matriculas_aeri (complemento_status, complemento_em)
    WHERE complemento_status IN ('PENDENTE','FALHA');
