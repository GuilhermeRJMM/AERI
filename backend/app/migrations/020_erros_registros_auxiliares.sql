CREATE TABLE IF NOT EXISTS registros_auxiliares_erros_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    modo VARCHAR(20) NOT NULL DEFAULT 'INICIAL',
    erro TEXT NOT NULL,
    tentativas INTEGER NOT NULL DEFAULT 1,
    primeira_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reg_aux_erros_tentativa
    ON registros_auxiliares_erros_aeri (ultima_tentativa_em ASC, numero ASC);
