-- Campos de identificação do imóvel exigidos pelo Mapa do Registro de
-- Imóveis (Manual Técnico Operacional, 3.4.5.2 / Manual da API, item 6).
--
-- Vão num JSONB só, e não em colunas próprias, porque são atributos de um
-- formulário externo: o quadro do ONR já mudou três vezes só no histórico
-- de versões do manual (1.1, 1.2 e 1.3), e acompanhar isso com ALTER
-- TABLE encheria o esquema de colunas que o AERI não consulta nem indexa.
-- O que o AERI de fato usa -- área, perímetro, anel -- continua em coluna.
ALTER TABLE poligonos_aeri
    ADD COLUMN IF NOT EXISTS dados_mapa JSONB NOT NULL DEFAULT '{}'::jsonb;
