-- Evolução aditiva: mantém índices, resultados e cursores existentes.
CREATE TABLE IF NOT EXISTS fila_registros_auxiliares_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    motivo VARCHAR(40) NOT NULL,
    solicitada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_fila_auxiliares_vencida
    ON fila_registros_auxiliares_aeri (proxima_tentativa_em, solicitada_em);

ALTER TABLE fila_protocolos_busca_aeri
    ADD COLUMN IF NOT EXISTS solicitada_em TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Somente assinatura do resumo, nunca texto integral, nomes ou documentos.
CREATE TABLE IF NOT EXISTS sinais_protocolos_indice_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    assinatura CHAR(64) NOT NULL,
    verificado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
