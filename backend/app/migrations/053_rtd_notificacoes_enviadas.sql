-- Registra tentativas de saída sem guardar CPF, endereços ou documentos enviados.
-- A chave de operação torna o clique repetido idempotente dentro do AERI.
CREATE TABLE IF NOT EXISTS rtd_notificacao_envios_aeri (
    id UUID PRIMARY KEY,
    chave_operacao UUID NOT NULL UNIQUE,
    intimacao_id UUID NOT NULL REFERENCES intimacoes_aeri(id),
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario),
    estado VARCHAR(24) NOT NULL CHECK (estado IN (
        'ENVIANDO', 'CRIADO', 'CRIADO_REVISAR', 'HOMOLOGACAO_OK', 'INCERTO',
        'FALHA_ARQUIVO', 'FALHA_VALIDACAO', 'RECUSADO'
    )),
    protocolo VARCHAR(40),
    cartorio_id INTEGER NOT NULL,
    arquivo_id INTEGER,
    ambiente VARCHAR(16) NOT NULL DEFAULT 'producao'
        CHECK (ambiente IN ('producao', 'homologacao')),
    erro VARCHAR(240),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alterado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE rtd_notificacao_envios_aeri
    DROP CONSTRAINT IF EXISTS rtd_notificacao_envios_aeri_estado_check;
ALTER TABLE rtd_notificacao_envios_aeri
    ADD CONSTRAINT rtd_notificacao_envios_aeri_estado_check CHECK (estado IN (
        'ENVIANDO', 'CRIADO', 'CRIADO_REVISAR', 'HOMOLOGACAO_OK', 'INCERTO',
        'FALHA_ARQUIVO', 'FALHA_VALIDACAO', 'RECUSADO'
    ));
CREATE INDEX IF NOT EXISTS idx_rtd_envios_intimacao
    ON rtd_notificacao_envios_aeri(intimacao_id, criado_em DESC);
