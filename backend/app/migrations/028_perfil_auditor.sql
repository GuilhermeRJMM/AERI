ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_revisar_auditoria BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE usuarios_aeri
    DROP CONSTRAINT IF EXISTS usuarios_aeri_perfil_valido;

ALTER TABLE usuarios_aeri ADD CONSTRAINT usuarios_aeri_perfil_valido
    CHECK (perfil IN ('ADMIN', 'SUBSTITUTO', 'AUDITOR', 'SUPERVISOR', 'CONFERENTE', 'PRODUTOR'));

UPDATE usuarios_aeri
SET pode_processar_matricula=TRUE,
    pode_revisar_auditoria=TRUE,
    pode_processar_incra=FALSE,
    pode_gerenciar_custas=FALSE,
    pode_ver_intimacoes=FALSE,
    pode_criar_intimacoes=FALSE,
    pode_alterar_intimacoes=FALSE,
    pode_conferir_intimacoes=FALSE
WHERE perfil='AUDITOR';
