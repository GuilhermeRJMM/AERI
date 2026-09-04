-- A indexacao de matriculas e de registros auxiliares avanca em lotes, e quem
-- a empurrava era uma aba do navegador em laco. A auditoria de 30 dias mostra
-- 4.605 chamadas de sincronizar_busca_titularidade e 2.559 de registros
-- auxiliares -- 68% de tudo que o AERI registra --, com picos as 23h, 00h e 01h:
-- gente deixando a tela aberta de madrugada, cada lote gastando CPU na Vercel.
-- O cron diario nao da conta: sozinho, a revisao pendente levaria anos.
-- Estas colunas e esta tabela deixam o executor da serventia assumir o laco.
CREATE TABLE IF NOT EXISTS executores_aeri (
 maquina VARCHAR(120) PRIMARY KEY,
 visto_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 codigo_de TIMESTAMPTZ,
 ciclos BIGINT NOT NULL DEFAULT 0
);

-- Freio de mao: o executor roda sem ninguem olhando e consome a API da Tri7.
-- Pausar precisa ser possivel sem desinstalar a tarefa nem editar codigo.
ALTER TABLE sincronizacao_matriculas_busca_aeri
 ADD COLUMN IF NOT EXISTS indexacao_pausada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sincronizacao_registros_auxiliares_aeri
 ADD COLUMN IF NOT EXISTS indexacao_pausada BOOLEAN NOT NULL DEFAULT FALSE;
