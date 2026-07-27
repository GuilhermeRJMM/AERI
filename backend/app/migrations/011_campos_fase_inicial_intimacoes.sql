ALTER TABLE intimacoes_aeri
    ADD COLUMN IF NOT EXISTS protocolo_rtd VARCHAR(17),
    ADD COLUMN IF NOT EXISTS numero_os_tri7 VARCHAR(40),
    ADD COLUMN IF NOT EXISTS protocolo_tri7 VARCHAR(40),
    ADD COLUMN IF NOT EXISTS certidao_decurso_prazo VARCHAR(160),
    ADD COLUMN IF NOT EXISTS data_intimacao DATE,
    ADD COLUMN IF NOT EXISTS data_certificacao DATE,
    ADD COLUMN IF NOT EXISTS valor_pago_onr NUMERIC(12, 2) NOT NULL DEFAULT 530.07,
    ADD COLUMN IF NOT EXISTS valor_usado NUMERIC(12, 2) NOT NULL DEFAULT 0.00;

ALTER TABLE intimacoes_aeri
    DROP CONSTRAINT IF EXISTS intimacoes_aeri_protocolo_rtd_valido,
    DROP CONSTRAINT IF EXISTS intimacoes_aeri_valores_nao_negativos;

ALTER TABLE intimacoes_aeri
    ADD CONSTRAINT intimacoes_aeri_protocolo_rtd_valido
        CHECK (protocolo_rtd IS NULL OR protocolo_rtd ~ '^[0-9]{17}$'),
    ADD CONSTRAINT intimacoes_aeri_valores_nao_negativos
        CHECK (valor_pago_onr >= 0 AND valor_usado >= 0);
