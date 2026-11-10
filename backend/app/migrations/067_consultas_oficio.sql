-- Captura externa separada: nenhuma alteração em intimacoes_aeri ou RTD.
-- Uma captura por serventia, sem acumular cópias do histórico do portal.
CREATE TABLE IF NOT EXISTS consultas_oficio_aeri (
    cartorio VARCHAR(10) PRIMARY KEY,
    consultado_em TIMESTAMPTZ NOT NULL,
    importado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    usuario VARCHAR(160) NOT NULL,
    captura JSONB NOT NULL,
    CHECK (cartorio ~ '^[1-9][0-9]{0,9}$'),
    CHECK (jsonb_typeof(captura) = 'object')
);
