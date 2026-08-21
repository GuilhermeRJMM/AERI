-- Busca textual eficiente e documentos protegidos no Registro Auxiliar.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pg_trgm indisponível (%). Busca continua funcional sem GIN.', SQLERRM;
END;
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS idx_busca_proprietario_nome_trgm
            ON proprietarios_matriculas_busca_aeri USING GIN (nome_busca gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS idx_reg_aux_nomes_trgm
            ON registros_auxiliares_aeri USING GIN (nomes_busca gin_trgm_ops);
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_busca_ausencias_reconsulta
    ON matriculas_busca_aeri (consultado_em, numero)
    WHERE situacao IN ('NAO_ENCONTRADA', 'SEM_TEXTO');

CREATE INDEX IF NOT EXISTS idx_auditorias_alertas_gin
    ON auditorias_matriculas_aeri USING GIN (alertas);

ALTER TABLE registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS documentos_hash JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS documentos_hash_versao SMALLINT;

ALTER TABLE registros_auxiliares_aeri
    DROP CONSTRAINT IF EXISTS reg_aux_hash_versao_valida;
ALTER TABLE registros_auxiliares_aeri
    ADD CONSTRAINT reg_aux_hash_versao_valida
    CHECK (documentos_hash_versao IS NULL OR documentos_hash_versao > 0);

CREATE INDEX IF NOT EXISTS idx_reg_aux_documentos_hash
    ON registros_auxiliares_aeri USING GIN (documentos_hash);
DROP INDEX IF EXISTS idx_reg_aux_documentos;

-- Elimina documentos completos do índice antigo imediatamente. Os registros
-- serão recompostos pelo modo REVISAO com HMAC e apresentação mascarada.
UPDATE registros_auxiliares_aeri r
SET pessoas = COALESCE((
        SELECT jsonb_agg((p - 'documento') || jsonb_build_object('documento', ''))
        FROM jsonb_array_elements(r.pessoas) AS p
    ), '[]'::jsonb),
    documentos_busca = '',
    documentos_hash = '[]'::jsonb,
    documentos_hash_versao = NULL;

UPDATE sincronizacao_registros_auxiliares_aeri
SET proximo_revisao=1, atualizado_em=NOW()
WHERE id=1;
