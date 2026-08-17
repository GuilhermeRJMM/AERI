ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_acessar_livro_protocolos BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_acessar_buscas BOOLEAN NOT NULL DEFAULT FALSE;

-- Livro de Protocolos e Buscas ficavam pendurados em pode_processar_matricula.
-- Quem já usava os dois módulos por causa dessa permissão emprestada mantém o
-- acesso; a separação só passa a valer para concessões futuras.
UPDATE usuarios_aeri
SET pode_acessar_livro_protocolos=TRUE,
    pode_acessar_buscas=TRUE
WHERE pode_processar_matricula=TRUE
   OR perfil IN ('ADMIN', 'SUBSTITUTO');
