ALTER TABLE matriculas_busca_aeri
    ADD COLUMN IF NOT EXISTS documentos_hash_versao SMALLINT;

ALTER TABLE matriculas_busca_aeri
    DROP CONSTRAINT IF EXISTS matricula_busca_hash_versao_valida;

ALTER TABLE matriculas_busca_aeri
    ADD CONSTRAINT matricula_busca_hash_versao_valida
    CHECK (documentos_hash_versao IS NULL OR documentos_hash_versao > 0);

-- Registros anteriores permanecem sem versão e serão priorizados pelo modo
-- REVISAO. O texto registral não é armazenado; o novo HMAC só pode ser criado
-- consultando novamente a matrícula na Tri7.
UPDATE sincronizacao_matriculas_busca_aeri
SET proximo_revisao = 1,
    atualizado_em = NOW()
WHERE id = 1;
