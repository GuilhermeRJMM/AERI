-- Presenca do executor nao basta: ele pode estar vivo e sem conseguir indexar,
-- por falta da chave do indice na maquina da serventia. Se o cron da Vercel se
-- abstivesse so por ver a batida, a indexacao pararia dos dois lados ao mesmo
-- tempo, em silencio. Esta coluna separa "esta rodando" de "esta dando conta".
ALTER TABLE executores_aeri
 ADD COLUMN IF NOT EXISTS indexa BOOLEAN NOT NULL DEFAULT FALSE;
