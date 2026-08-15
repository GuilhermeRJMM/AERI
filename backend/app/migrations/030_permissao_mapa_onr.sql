ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_acessar_mapa_onr BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE usuarios_aeri
SET pode_acessar_mapa_onr=TRUE
WHERE perfil IN ('ADMIN', 'SUBSTITUTO');
