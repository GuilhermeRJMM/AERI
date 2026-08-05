ALTER TABLE registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS situacao VARCHAR(20) NOT NULL DEFAULT 'ATIVO';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'registro_auxiliar_situacao_valida'
    ) THEN
        ALTER TABLE registros_auxiliares_aeri
            ADD CONSTRAINT registro_auxiliar_situacao_valida
            CHECK (situacao IN ('ATIVO', 'BAIXADO'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_reg_aux_situacao
    ON registros_auxiliares_aeri (situacao, numero DESC);

DELETE FROM registros_auxiliares_aeri;

UPDATE sincronizacao_registros_auxiliares_aeri
SET proximo_inicial=1,
    proximo_revisao=1,
    ultima_sincronizacao=NULL,
    atualizado_em=NOW()
WHERE id=1;
