ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_processar_matricula BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS pode_processar_incra BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS pode_ver_intimacoes BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS pode_criar_intimacoes BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS pode_alterar_intimacoes BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS pode_conferir_intimacoes BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE usuarios_aeri
SET perfil='OPERADOR'
WHERE perfil='CONSULTA';

UPDATE usuarios_aeri
SET pode_processar_matricula=TRUE,
    pode_processar_incra=TRUE,
    pode_ver_intimacoes=TRUE,
    pode_criar_intimacoes=TRUE,
    pode_alterar_intimacoes=TRUE,
    pode_conferir_intimacoes=TRUE
WHERE perfil='ADMIN';

ALTER TABLE usuarios_aeri
    DROP CONSTRAINT IF EXISTS usuarios_aeri_perfil_valido;

ALTER TABLE usuarios_aeri ADD CONSTRAINT usuarios_aeri_perfil_valido
    CHECK (perfil IN ('ADMIN', 'OPERADOR'));
