-- Registra todos os números consultados na Tri7, inclusive ausências, para
-- que registros disponibilizados tardiamente possam ser encontrados depois.
ALTER TABLE sincronizacao_registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS proximo_lacuna INTEGER NOT NULL DEFAULT 1;
ALTER TABLE sincronizacao_registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS ciclo_automatico BIGINT NOT NULL DEFAULT 0;

ALTER TABLE registros_auxiliares_erros_aeri
    ADD COLUMN IF NOT EXISTS proxima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS registros_auxiliares_varredura_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    resultado VARCHAR(16) NOT NULL CHECK (resultado IN ('ENCONTRADO', 'AUSENTE', 'ERRO')),
    consultado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    proxima_consulta_em TIMESTAMPTZ,
    tentativas INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0)
);

CREATE INDEX IF NOT EXISTS idx_reg_aux_varredura_pendente
    ON registros_auxiliares_varredura_aeri (proxima_consulta_em, numero)
    WHERE resultado IN ('AUSENTE', 'ERRO');

-- Os itens já indexados são consultas confirmadas. Não se presume nada sobre
-- os números que ainda não possuem linha no índice.
INSERT INTO registros_auxiliares_varredura_aeri
    (numero, resultado, consultado_em, proxima_consulta_em, tentativas)
SELECT numero, 'ENCONTRADO', consultado_em, NULL, 0
FROM registros_auxiliares_aeri
ON CONFLICT (numero) DO NOTHING;

-- Corrige marcadores antigos que foram adiantados pelo limite de varredura.
-- A partir daqui, ultimo_existente volta a significar apenas número confirmado.
UPDATE sincronizacao_registros_auxiliares_aeri
SET ultimo_existente = COALESCE(
        (SELECT MAX(numero) FROM registros_auxiliares_aeri), 0
    ),
    limite_inicial = GREATEST(
        limite_inicial,
        COALESCE((SELECT MAX(numero) FROM registros_auxiliares_aeri), 0)
    ),
    proximo_lacuna = GREATEST(
        1,
        COALESCE((SELECT MAX(numero) - 20 FROM registros_auxiliares_aeri), 1)
    ),
    atualizado_em = NOW()
WHERE id = 1;
