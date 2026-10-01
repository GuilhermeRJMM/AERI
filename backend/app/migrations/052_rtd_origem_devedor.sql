-- Permite complementar destinatários de novas diligências sem sobrescrever edição humana.
ALTER TABLE intimacoes_aeri ADD COLUMN IF NOT EXISTS devedor_rtd_valor VARCHAR(160);
