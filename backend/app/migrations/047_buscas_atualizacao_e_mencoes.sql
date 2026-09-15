-- Evolução aditiva: o índice de menções nunca substitui titulares atuais.
ALTER TABLE matriculas_busca_aeri ADD COLUMN IF NOT EXISTS indice_busca_versao INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matriculas_busca_aeri ADD COLUMN IF NOT EXISTS falha_consulta_em TIMESTAMPTZ;
ALTER TABLE matriculas_busca_erros_aeri ADD COLUMN IF NOT EXISTS proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE sincronizacao_matriculas_busca_aeri ADD COLUMN IF NOT EXISTS ciclo_automatico BIGINT NOT NULL DEFAULT 0;
ALTER TABLE sincronizacao_matriculas_busca_aeri ADD COLUMN IF NOT EXISTS sinais_verificados_em TIMESTAMPTZ;
ALTER TABLE sincronizacao_matriculas_busca_aeri ADD COLUMN IF NOT EXISTS sinais_trava_ate TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_busca_reconsulta ON matriculas_busca_aeri (consultado_em, numero);
CREATE INDEX IF NOT EXISTS idx_busca_erros_vencidos ON matriculas_busca_erros_aeri (proxima_tentativa_em, numero);

CREATE TABLE IF NOT EXISTS mencoes_matriculas_busca_aeri (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 matricula_numero INTEGER NOT NULL REFERENCES matriculas_busca_aeri(numero) ON DELETE CASCADE,
 ato VARCHAR(40) NOT NULL,
 papel VARCHAR(32) NOT NULL CHECK(papel IN ('PROPRIETARIO_INICIAL','ADQUIRENTE','TRANSMITENTE','QUALIFICADO','RETIFICACAO')),
 nome VARCHAR(300) NOT NULL,
 nome_busca VARCHAR(300) NOT NULL,
 documento_hash CHAR(64),
 documento_mascarado VARCHAR(24) NOT NULL DEFAULT '',
 tipo_documento VARCHAR(8) NOT NULL DEFAULT '',
 UNIQUE(matricula_numero,ato,papel,nome_busca,documento_mascarado)
);
CREATE INDEX IF NOT EXISTS idx_mencoes_matricula ON mencoes_matriculas_busca_aeri(matricula_numero);
CREATE INDEX IF NOT EXISTS idx_mencoes_documento ON mencoes_matriculas_busca_aeri(documento_hash) WHERE documento_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mencoes_nome ON mencoes_matriculas_busca_aeri(nome_busca text_pattern_ops);

CREATE TABLE IF NOT EXISTS fila_matriculas_busca_aeri (
 numero INTEGER PRIMARY KEY CHECK(numero>0),
 motivo VARCHAR(40) NOT NULL,
 solicitada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS fila_protocolos_busca_aeri (
 numero INTEGER PRIMARY KEY CHECK(numero>0),
 proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 tentativas INTEGER NOT NULL DEFAULT 0
);
INSERT INTO fila_matriculas_busca_aeri(numero,motivo)
SELECT m.numero,'LACUNA_EXTRACAO' FROM matriculas_busca_aeri m
LEFT JOIN auditorias_matriculas_aeri a ON a.matricula_numero=m.numero
WHERE m.situacao='ATIVA' AND (m.quantidade_proprietarios=0 OR a.veredito_cadeia='REVISAR')
ON CONFLICT DO NOTHING;
