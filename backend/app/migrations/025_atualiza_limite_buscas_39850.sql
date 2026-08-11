ALTER TABLE sincronizacao_matriculas_busca_aeri
    ALTER COLUMN limite_inicial SET DEFAULT 39850,
    ALTER COLUMN ultimo_conhecido SET DEFAULT 39850;

UPDATE sincronizacao_matriculas_busca_aeri
SET limite_inicial = GREATEST(limite_inicial, 39850),
    ultimo_conhecido = GREATEST(ultimo_conhecido, 39850),
    atualizado_em = NOW()
WHERE id = 1;
