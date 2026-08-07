-- A migração 010 preencheu a fase só para uma lista fixa de protocolos que
-- existiam naquele momento. Qualquer intimação fora dessa lista (anterior à
-- migração ou reimportada depois) ficou com fase=NULL -- valor permitido
-- pela CHECK constraint, mas que nunca bate com nenhuma das 3 abas do
-- frontend ('INTIMACAO'/'EDITAL'/'CONSOLIDACAO' por igualdade exata), então
-- a intimação some visualmente de todos os filtros mesmo continuando
-- cadastrada (e bloqueando um novo cadastro com o mesmo protocolo).
UPDATE intimacoes_aeri
SET fase = 'INTIMACAO'
WHERE fase IS NULL;
