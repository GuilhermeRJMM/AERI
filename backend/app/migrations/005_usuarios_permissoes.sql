ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS nome VARCHAR(160) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS perfil VARCHAR(20) NOT NULL DEFAULT 'ADMIN',
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS deve_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'usuarios_aeri_perfil_valido'
    ) THEN
        ALTER TABLE usuarios_aeri ADD CONSTRAINT usuarios_aeri_perfil_valido
            CHECK (perfil IN ('ADMIN', 'OPERADOR', 'CONSULTA'));
    END IF;
END $$;

UPDATE usuarios_aeri SET nome=usuario WHERE nome='';
