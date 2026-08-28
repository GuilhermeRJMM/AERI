-- Consolida recursos operacionais aprovados sem apagar o modelo legado.

ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS senha_temporaria_expira_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mfa_segredo_criptografado TEXT,
    ADD COLUMN IF NOT EXISTS mfa_ativo BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO permissoes_aeri (chave, nome, modulo, ordem) VALUES
('consultar_registro_auxiliar', 'Consultar Registro Auxiliar', 'Registro Auxiliar', 91),
('revisar_registro_auxiliar', 'Revisar Registro Auxiliar', 'Registro Auxiliar', 92),
('sincronizar_registro_auxiliar', 'Sincronizar Registro Auxiliar', 'Registro Auxiliar', 93)
ON CONFLICT (chave) DO NOTHING;
INSERT INTO usuarios_permissoes_aeri (usuario, permissao, concedida)
SELECT up.usuario, nova.permissao, TRUE
FROM usuarios_permissoes_aeri up
CROSS JOIN (VALUES ('consultar_registro_auxiliar'), ('revisar_registro_auxiliar'),
                   ('sincronizar_registro_auxiliar')) nova(permissao)
WHERE up.permissao='gerenciar_custas' AND up.concedida=TRUE
ON CONFLICT (usuario, permissao) DO NOTHING;

CREATE TABLE IF NOT EXISTS custas_precos_aeri (
    id BIGSERIAL PRIMARY KEY,
    servico VARCHAR(80) NOT NULL,
    valor NUMERIC(12,2) NOT NULL CHECK (valor >= 0),
    vigencia_inicio DATE NOT NULL,
    vigencia_fim DATE,
    criado_por VARCHAR(80) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_custas_precos_vigencia
    ON custas_precos_aeri (servico, vigencia_inicio);
INSERT INTO custas_precos_aeri (servico, valor, vigencia_inicio)
VALUES ('CERTIDAO_REGISTRO_AUXILIAR', 139.93, DATE '2026-01-01')
ON CONFLICT (servico, vigencia_inicio) DO NOTHING;

ALTER TABLE intimacoes_aeri
    ADD COLUMN IF NOT EXISTS excluida_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS excluida_por VARCHAR(80),
    ADD COLUMN IF NOT EXISTS checklist_desistencia JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE eventos_intimacao_aeri DROP CONSTRAINT IF EXISTS eventos_intimacao_aeri_tipo_check;
ALTER TABLE eventos_intimacao_aeri ADD CONSTRAINT eventos_intimacao_aeri_tipo_check CHECK (
    tipo IN ('CRIACAO', 'ALTERACAO', 'CONFERENCIA', 'ANDAMENTO', 'EXCLUSAO',
             'RESTAURACAO', 'LANCAMENTO_FINANCEIRO', 'CHECKLIST')
);

CREATE TABLE IF NOT EXISTS feriados_aeri (
    data DATE PRIMARY KEY,
    descricao VARCHAR(160) NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_por VARCHAR(80) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lancamentos_intimacao_aeri (
    id UUID PRIMARY KEY,
    intimacao_id UUID NOT NULL REFERENCES intimacoes_aeri(id),
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('CREDITO', 'REPASSE', 'ESTORNO')),
    valor NUMERIC(12,2) NOT NULL CHECK (valor > 0),
    descricao VARCHAR(240),
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lancamentos_intimacao
    ON lancamentos_intimacao_aeri (intimacao_id, criado_em);

CREATE INDEX IF NOT EXISTS idx_intimacoes_lixeira
    ON intimacoes_aeri (excluida_em, fase, protocolo);
