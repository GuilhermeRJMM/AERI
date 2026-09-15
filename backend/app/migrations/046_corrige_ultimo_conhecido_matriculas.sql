-- `ultimo_conhecido` representa a maior matrícula cujo texto foi realmente
-- localizado na Tri7. Versões anteriores copiavam para ele o limite digitado
-- na carga inicial, mesmo quando os números finais eram inexistentes.
-- Isso fazia a busca de novos começar depois da verdadeira fronteira do acervo.
ALTER TABLE sincronizacao_matriculas_busca_aeri
    ALTER COLUMN ultimo_conhecido SET DEFAULT 0;

UPDATE sincronizacao_matriculas_busca_aeri
SET ultimo_conhecido = COALESCE(
        (SELECT MAX(numero)
         FROM matriculas_busca_aeri
         WHERE texto_hash IS NOT NULL),
        0
    ),
    atualizado_em = NOW()
WHERE id = 1;
