ALTER TABLE usuarios_aeri
    DROP CONSTRAINT IF EXISTS usuarios_aeri_perfil_valido;

UPDATE usuarios_aeri
SET perfil='CONFERENTE'
WHERE perfil='OPERADOR';

ALTER TABLE usuarios_aeri ADD CONSTRAINT usuarios_aeri_perfil_valido
    CHECK (perfil IN ('ADMIN', 'SUBSTITUTO', 'SUPERVISOR', 'CONFERENTE', 'PRODUTOR'));

UPDATE usuarios_aeri
SET pode_processar_matricula=TRUE,
    pode_processar_incra=TRUE,
    pode_ver_intimacoes=TRUE,
    pode_criar_intimacoes=TRUE,
    pode_alterar_intimacoes=TRUE,
    pode_conferir_intimacoes=TRUE
WHERE perfil IN ('ADMIN', 'SUBSTITUTO');
