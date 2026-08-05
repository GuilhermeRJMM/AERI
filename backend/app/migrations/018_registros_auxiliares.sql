CREATE TABLE IF NOT EXISTS registros_auxiliares_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    texto_hash CHAR(64) NOT NULL,
    modalidade VARCHAR(20) NOT NULL DEFAULT 'OUTROS',
    pessoas JSONB NOT NULL DEFAULT '[]'::jsonb,
    nomes_busca TEXT NOT NULL DEFAULT '',
    documentos_busca TEXT NOT NULL DEFAULT '',
    produtos JSONB NOT NULL DEFAULT '[]'::jsonb,
    safras JSONB NOT NULL DEFAULT '[]'::jsonb,
    consultado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT registro_auxiliar_modalidade_valida
        CHECK (modalidade IN ('PENHOR', 'ALIENAÇÃO', 'OUTROS'))
);

CREATE INDEX IF NOT EXISTS idx_reg_aux_nomes
    ON registros_auxiliares_aeri (nomes_busca text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_reg_aux_documentos
    ON registros_auxiliares_aeri (documentos_busca text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_reg_aux_modalidade
    ON registros_auxiliares_aeri (modalidade, numero DESC);
CREATE INDEX IF NOT EXISTS idx_reg_aux_produtos
    ON registros_auxiliares_aeri USING GIN (produtos);
CREATE INDEX IF NOT EXISTS idx_reg_aux_safras
    ON registros_auxiliares_aeri USING GIN (safras);

CREATE TABLE IF NOT EXISTS sincronizacao_registros_auxiliares_aeri (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    limite_inicial INTEGER NOT NULL DEFAULT 29538,
    proximo_inicial INTEGER NOT NULL DEFAULT 1,
    ultimo_existente INTEGER NOT NULL DEFAULT 29538,
    proximo_revisao INTEGER NOT NULL DEFAULT 1,
    ultima_sincronizacao TIMESTAMPTZ,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO sincronizacao_registros_auxiliares_aeri
    (id, limite_inicial, proximo_inicial, ultimo_existente, proximo_revisao)
VALUES (1, 29538, 1, 29538, 1)
ON CONFLICT (id) DO NOTHING;
