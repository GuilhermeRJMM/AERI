-- RTD é acompanhamento externo: não altera fase, finanças ou andamento interno.
CREATE TABLE IF NOT EXISTS rtd_sincronizacao_aeri (
    id INTEGER PRIMARY KEY CHECK (id=1),
    desde DATE, pagina INTEGER NOT NULL DEFAULT 1,
    inicio_rodada TIMESTAMPTZ, proxima_consulta TIMESTAMPTZ,
    ultima_consulta TIMESTAMPTZ, ultimo_sucesso TIMESTAMPTZ,
    erro VARCHAR(240), atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO rtd_sincronizacao_aeri(id) VALUES (1) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS rtd_pedidos_aeri (
    protocolo VARCHAR(17) PRIMARY KEY CHECK (protocolo ~ '^[0-9]{17}$'),
    intimacao_id UUID REFERENCES intimacoes_aeri(id),
    in_documento VARCHAR(11), candidatos JSONB NOT NULL DEFAULT '[]',
    vinculo VARCHAR(40) NOT NULL DEFAULT 'PENDENTE',
    dados JSONB NOT NULL DEFAULT '{}', resumo_hash VARCHAR(64),
    documento_hash VARCHAR(64), versao INTEGER NOT NULL DEFAULT 0,
    pendente BOOLEAN NOT NULL DEFAULT TRUE,
    tentar_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erro VARCHAR(240), consultado_em TIMESTAMPTZ,
    alterado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rtd_intimacao ON rtd_pedidos_aeri(intimacao_id);
CREATE INDEX IF NOT EXISTS idx_rtd_fila ON rtd_pedidos_aeri(tentar_em) WHERE pendente;
CREATE TABLE IF NOT EXISTS rtd_eventos_aeri (
    id BIGSERIAL PRIMARY KEY,
    protocolo VARCHAR(17) NOT NULL REFERENCES rtd_pedidos_aeri(protocolo),
    versao INTEGER NOT NULL,
    anterior JSONB NOT NULL, atual JSONB NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(protocolo, versao)
);
CREATE TABLE IF NOT EXISTS rtd_leituras_aeri (
    protocolo VARCHAR(17) NOT NULL REFERENCES rtd_pedidos_aeri(protocolo),
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    versao INTEGER NOT NULL,
    lido_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(protocolo, usuario)
);
