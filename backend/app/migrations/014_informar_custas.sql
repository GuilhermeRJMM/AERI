ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_gerenciar_custas BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE usuarios_aeri
SET pode_gerenciar_custas=TRUE
WHERE perfil IN ('ADMIN', 'SUBSTITUTO');

CREATE TABLE IF NOT EXISTS custas_livro3_aeri (
    id UUID PRIMARY KEY,
    pedido VARCHAR(20) NOT NULL UNIQUE,
    nome VARCHAR(180) NOT NULL,
    documento VARCHAR(20) NOT NULL,
    modalidade VARCHAR(30) NOT NULL,
    produto VARCHAR(80) NOT NULL DEFAULT 'NÃO CONSTA',
    safra VARCHAR(20) NOT NULL DEFAULT 'NÃO CONSTA',
    resultado VARCHAR(20) NOT NULL DEFAULT 'PENDENTE',
    numero_registro VARCHAR(200) NOT NULL DEFAULT '',
    status VARCHAR(40) NOT NULL DEFAULT 'FAZER_PESQUISA',
    finalizado BOOLEAN NOT NULL DEFAULT FALSE,
    criado_por VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    atualizado_por VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ,
    CONSTRAINT custas_modalidade_valida CHECK (modalidade IN ('PENHOR', 'ALIENACAO_FIDUCIARIA')),
    CONSTRAINT custas_resultado_valido CHECK (resultado IN ('PENDENTE', 'POSITIVA', 'NEGATIVA')),
    CONSTRAINT custas_status_valido CHECK (status IN (
        'FAZER_PESQUISA', 'BUSCA_REALIZADA', 'DUPLICADO_DEVOLVIDO',
        'PAGO_PROCESSANDO', 'CUSTAS_INFORMADAS', 'RESPONDIDO',
        'SEM_PAGAMENTO', 'CUSTAS_ERRADAS'
    ))
);

CREATE INDEX IF NOT EXISTS idx_custas_livro3_fila
    ON custas_livro3_aeri (finalizado, atualizado_em DESC);
CREATE INDEX IF NOT EXISTS idx_custas_livro3_status
    ON custas_livro3_aeri (status, finalizado);

CREATE TABLE IF NOT EXISTS eventos_custas_livro3_aeri (
    id BIGSERIAL PRIMARY KEY,
    item_id UUID NOT NULL REFERENCES custas_livro3_aeri(id),
    pedido VARCHAR(20) NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    usuario VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eventos_custas_item
    ON eventos_custas_livro3_aeri (item_id, criado_em DESC);
