ALTER TABLE rtd_pedidos_aeri ADD COLUMN IF NOT EXISTS destinatarios JSONB NOT NULL DEFAULT '[]'::jsonb;
-- Reprocessa PDFs já consultados antes da identificação dos destinatários.
UPDATE rtd_pedidos_aeri SET documento_hash=NULL,pendente=TRUE,tentar_em=NOW()
WHERE consultado_em IS NOT NULL;
