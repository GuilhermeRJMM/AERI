-- Pares (Dados do Título x Natureza Formal) confirmados manualmente como
-- corretos, apesar de a comparação por texto (livro_protocolos.py) não
-- reconhecer relação entre os dois -- ex.: "Contrato Particular Venda e
-- Compra" com natureza "Compra e Venda - PMCMV e/ou SFH", onde PMCMV/SFH é
-- uma modalidade de financiamento que só quem conhece o negócio sabe que
-- corresponde. titulo_tema/natureza_tema guardam o texto já normalizado
-- (normalizar_tema), do mesmo jeito que a regra compara -- é contra esses
-- dois campos que a checagem da próxima conferência é feita.
CREATE TABLE IF NOT EXISTS livro_protocolos_excecoes_natureza_aeri (
    id UUID PRIMARY KEY,
    titulo_tema TEXT NOT NULL,
    natureza_tema TEXT NOT NULL,
    titulo_original TEXT NOT NULL,
    natureza_original TEXT NOT NULL,
    criado_por VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (titulo_tema, natureza_tema)
);
