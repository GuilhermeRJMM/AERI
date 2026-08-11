UPDATE sincronizacao_matriculas_busca_aeri
SET proximo_inicial = 1,
    atualizado_em = NOW()
WHERE id = 1;
