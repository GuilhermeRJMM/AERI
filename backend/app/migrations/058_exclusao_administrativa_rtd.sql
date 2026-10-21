-- Tombstones administrativos impedem que uma sincronizaÃ§Ã£o futura recrie
-- protocolos RTD que o cartÃ³rio removeu conscientemente do AERI.
CREATE TABLE IF NOT EXISTS rtd_protocolos_excluidos_aeri (
    protocolo VARCHAR(17) PRIMARY KEY CHECK (protocolo ~ '^[0-9]{17}$'),
    in_protocolo VARCHAR(20) NOT NULL,
    excluido_por VARCHAR(80) NOT NULL,
    excluido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rtd_excluidos_in
    ON rtd_protocolos_excluidos_aeri(in_protocolo, excluido_em DESC);
