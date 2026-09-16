-- Recibos permanecem mesmo após reabertura do pedido: repetir o mesmo evento
-- devolve o recibo original e não reaplica a finalização.
CREATE TABLE IF NOT EXISTS recibos_certidoes_l3bot_aeri (
    evento_id UUID PRIMARY KEY,
    pedido VARCHAR(20) NOT NULL,
    respondido_em TIMESTAMPTZ NOT NULL,
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    situacao VARCHAR(20) NOT NULL CHECK (
        situacao IN ('RECEBIDO', 'CONFIRMADO', 'JA_RESPONDIDO', 'NAO_ENCONTRADO', 'CONFLITO')
    )
);
CREATE INDEX IF NOT EXISTS idx_recibos_l3bot_pedido
    ON recibos_certidoes_l3bot_aeri (pedido, recebido_em DESC);
