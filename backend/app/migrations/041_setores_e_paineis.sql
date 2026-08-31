-- Migração aditiva: preserva usuários e permissões existentes.
-- Ponto de retorno: somente acessos; não copia senhas, sessões ou documentos.
-- A fotografia é imutável por versão e não é sobrescrita em uma reaplicação.
CREATE TABLE IF NOT EXISTS backups_acessos_aeri (
 versao VARCHAR(120) PRIMARY KEY,
 criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 catalogo JSONB NOT NULL,
 perfis JSONB NOT NULL,
 concessoes JSONB NOT NULL,
 cargos JSONB NOT NULL
);
INSERT INTO backups_acessos_aeri (versao,catalogo,perfis,concessoes,cargos)
SELECT 'antes_setores_20260831',
 COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM permissoes_aeri p),'[]'::jsonb),
 COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM perfis_permissoes_aeri p),'[]'::jsonb),
 COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM usuarios_permissoes_aeri p),'[]'::jsonb),
 COALESCE((SELECT jsonb_agg(jsonb_build_object('usuario',u.usuario,'perfil',u.perfil)) FROM usuarios_aeri u),'[]'::jsonb)
ON CONFLICT (versao) DO NOTHING;

ALTER TABLE usuarios_aeri DROP CONSTRAINT IF EXISTS usuarios_aeri_perfil_valido;
ALTER TABLE usuarios_aeri ADD CONSTRAINT usuarios_aeri_perfil_valido
CHECK (perfil IN ('ADMIN','SUBSTITUTO','SUPERVISOR','USUARIO','CONFERENTE','PRODUTOR','AUDITOR'));

INSERT INTO permissoes_aeri (chave,nome,modulo,ordem) VALUES
('acessar_certidao','Setor Certidão','Setores',1),
('acessar_rgi','Setor RGI — Produção e Conferência','Setores',2),
('gerenciar_usuarios','Usuários e Acessos','Administração',3),
('configurar_sistema','Integrações e agendamentos','Administração',4),
('acessar_contratos','Contratos e Minutas','RGI',75)
ON CONFLICT DO NOTHING;

INSERT INTO usuarios_permissoes_aeri (usuario,permissao,concedida)
SELECT DISTINCT u.usuario, CASE WHEN p.permissao IN
('processar_matricula','acessar_buscas','processar_incra','acessar_livro_protocolos',
 'gerenciar_custas','consultar_registro_auxiliar','revisar_registro_auxiliar',
 'sincronizar_registro_auxiliar','ver_intimacoes','criar_intimacoes','alterar_intimacoes','conferir_intimacoes')
THEN 'acessar_certidao' ELSE 'acessar_rgi' END, TRUE
FROM usuarios_aeri u CROSS JOIN LATERAL (
 SELECT up.permissao FROM usuarios_permissoes_aeri up WHERE up.usuario=u.usuario AND up.concedida=TRUE
 UNION
 SELECT pp.permissao FROM perfis_permissoes_aeri pp WHERE pp.perfil=u.perfil
 AND NOT EXISTS(SELECT 1 FROM usuarios_permissoes_aeri n WHERE n.usuario=u.usuario AND n.permissao=pp.permissao AND n.concedida=FALSE)
) p
WHERE p.permissao NOT IN ('acessar_certidao','acessar_rgi','gerenciar_usuarios','configurar_sistema')
ON CONFLICT DO NOTHING;
INSERT INTO perfis_permissoes_aeri (perfil,permissao) VALUES
('AUDITOR','acessar_certidao'),('AUDITOR','acessar_rgi') ON CONFLICT DO NOTHING;

-- Fotografia dos overrides atuais: os defaults novos não ampliam acessos antigos.
INSERT INTO usuarios_permissoes_aeri (usuario,permissao,concedida)
SELECT u.usuario,p.chave,EXISTS(SELECT 1 FROM perfis_permissoes_aeri pp
 WHERE pp.perfil=u.perfil AND pp.permissao=p.chave)
FROM usuarios_aeri u CROSS JOIN permissoes_aeri p WHERE u.perfil='SUPERVISOR'
ON CONFLICT DO NOTHING;
INSERT INTO perfis_permissoes_aeri (perfil,permissao)
SELECT 'SUPERVISOR',chave FROM permissoes_aeri WHERE chave NOT IN
('gerenciar_usuarios','ver_intimacoes','criar_intimacoes','alterar_intimacoes','conferir_intimacoes')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS automacoes_operacionais_aeri (
 chave VARCHAR(40) PRIMARY KEY,
 habilitada BOOLEAN NOT NULL DEFAULT FALSE,
 intervalo_minutos INTEGER NOT NULL DEFAULT 60 CHECK (intervalo_minutos BETWEEN 15 AND 1440),
 hora_inicio INTEGER NOT NULL DEFAULT 7 CHECK (hora_inicio BETWEEN 0 AND 23),
 hora_fim INTEGER NOT NULL DEFAULT 19 CHECK (hora_fim BETWEEN 1 AND 24),
 dias_semana JSONB NOT NULL DEFAULT '[0,1,2,3,4]'::jsonb,
 proxima_execucao TIMESTAMPTZ,
 ultima_tentativa TIMESTAMPTZ,
 ultimo_sucesso TIMESTAMPTZ,
 trava UUID,
 trava_ate TIMESTAMPTZ,
 atualizado_por VARCHAR(80) REFERENCES usuarios_aeri(usuario),
 atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK (hora_fim > hora_inicio)
);
INSERT INTO automacoes_operacionais_aeri (chave) VALUES ('livro_protocolos'),('intimacoes') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS execucoes_operacionais_aeri (
 id UUID PRIMARY KEY,
 chave VARCHAR(40) NOT NULL REFERENCES automacoes_operacionais_aeri(chave),
 data_alvo DATE NOT NULL,
 estado VARCHAR(20) NOT NULL,
 inicio TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 fim TIMESTAMPTZ,
 duracao_ms INTEGER,
 protocolos INTEGER NOT NULL DEFAULT 0,
 ocorrencias INTEGER NOT NULL DEFAULT 0,
 erro VARCHAR(200),
 resultado JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_execucoes_operacionais ON execucoes_operacionais_aeri(chave,inicio DESC);
