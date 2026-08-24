ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_acessar_gerador_notas BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE usuarios_aeri
SET pode_acessar_gerador_notas=TRUE
WHERE perfil IN ('ADMIN', 'SUBSTITUTO');
