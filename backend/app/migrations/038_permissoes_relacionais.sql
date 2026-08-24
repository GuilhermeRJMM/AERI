CREATE TABLE IF NOT EXISTS permissoes_aeri (
    chave VARCHAR(80) PRIMARY KEY,
    nome VARCHAR(120) NOT NULL,
    modulo VARCHAR(120) NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativa BOOLEAN NOT NULL DEFAULT TRUE,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS perfis_permissoes_aeri (
    perfil VARCHAR(30) NOT NULL,
    permissao VARCHAR(80) NOT NULL REFERENCES permissoes_aeri(chave) ON DELETE CASCADE,
    PRIMARY KEY (perfil, permissao)
);

CREATE TABLE IF NOT EXISTS usuarios_permissoes_aeri (
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    permissao VARCHAR(80) NOT NULL REFERENCES permissoes_aeri(chave) ON DELETE CASCADE,
    concedida BOOLEAN NOT NULL DEFAULT TRUE,
    atualizada_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (usuario, permissao)
);

INSERT INTO permissoes_aeri (chave, nome, modulo, ordem) VALUES
('processar_matricula', 'Matrículas', 'Registro de Imóveis', 10),
('revisar_auditoria', 'Auditoria registral', 'Registro de Imóveis', 20),
('acessar_mapa_onr', 'MAPA-ONR', 'Registro de Imóveis', 30),
('acessar_livro_protocolos', 'Livro de Protocolos', 'Registro de Imóveis', 40),
('acessar_buscas', 'Buscas', 'Registro de Imóveis', 50),
('acessar_poligonos', 'Polígonos', 'Registro de Imóveis', 60),
('acessar_gerador_notas', 'Gerador de Notas', 'Registro de Imóveis', 70),
('processar_incra', 'INCRA', 'Rotinas', 80),
('gerenciar_custas', 'Informar Custas', 'Certidões', 90),
('ver_intimacoes', 'Ver intimações', 'Intimações', 100),
('criar_intimacoes', 'Criar/importar intimações', 'Intimações', 110),
('alterar_intimacoes', 'Alterar intimações', 'Intimações', 120),
('conferir_intimacoes', 'Dar check em intimações', 'Intimações', 130)
ON CONFLICT (chave) DO NOTHING;

INSERT INTO perfis_permissoes_aeri (perfil, permissao) VALUES
('AUDITOR', 'processar_matricula'),
('AUDITOR', 'revisar_auditoria')
ON CONFLICT DO NOTHING;

INSERT INTO usuarios_permissoes_aeri (usuario, permissao)
SELECT usuario, permissao
FROM usuarios_aeri
CROSS JOIN LATERAL (VALUES
    ('processar_matricula', pode_processar_matricula),
    ('revisar_auditoria', pode_revisar_auditoria),
    ('acessar_mapa_onr', pode_acessar_mapa_onr),
    ('acessar_livro_protocolos', pode_acessar_livro_protocolos),
    ('acessar_buscas', pode_acessar_buscas),
    ('acessar_poligonos', pode_acessar_poligonos),
    ('acessar_gerador_notas', pode_acessar_gerador_notas),
    ('processar_incra', pode_processar_incra),
    ('gerenciar_custas', pode_gerenciar_custas),
    ('ver_intimacoes', pode_ver_intimacoes),
    ('criar_intimacoes', pode_criar_intimacoes),
    ('alterar_intimacoes', pode_alterar_intimacoes),
    ('conferir_intimacoes', pode_conferir_intimacoes)
) AS legado(permissao, concedida)
WHERE concedida=TRUE
ON CONFLICT (usuario, permissao) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_usuarios_permissoes_permissao
ON usuarios_permissoes_aeri (permissao, usuario) WHERE concedida=TRUE;
