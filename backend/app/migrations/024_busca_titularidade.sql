CREATE TABLE IF NOT EXISTS matriculas_busca_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    texto_hash CHAR(64),
    resultado_hash CHAR(64),
    situacao VARCHAR(24) NOT NULL DEFAULT 'REVISAR',
    situacao_origem VARCHAR(120) NOT NULL DEFAULT '',
    matriculas_sucessoras JSONB NOT NULL DEFAULT '[]'::jsonb,
    quantidade_proprietarios INTEGER NOT NULL DEFAULT 0,
    confianca VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
    motor_versao VARCHAR(30) NOT NULL DEFAULT '',
    consultado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT matricula_busca_situacao_valida
        CHECK (situacao IN ('ATIVA', 'ENCERRADA', 'INEXISTENTE', 'SEM_TEXTO', 'NAO_ENCONTRADA', 'REVISAR')),
    CONSTRAINT matricula_busca_confianca_valida
        CHECK (confianca IN ('ALTA', 'MEDIA', 'BAIXA'))
);

CREATE TABLE IF NOT EXISTS proprietarios_matriculas_busca_aeri (
    matricula_numero INTEGER NOT NULL REFERENCES matriculas_busca_aeri(numero) ON DELETE CASCADE,
    ordem SMALLINT NOT NULL CHECK (ordem > 0),
    nome VARCHAR(300) NOT NULL,
    nome_busca VARCHAR(300) NOT NULL,
    documento_hash CHAR(64),
    documento_mascarado VARCHAR(24) NOT NULL DEFAULT '',
    tipo_documento VARCHAR(8) NOT NULL DEFAULT '',
    proporcao VARCHAR(40) NOT NULL DEFAULT '100%',
    origem VARCHAR(80) NOT NULL DEFAULT 'Cadeia dominial',
    confianca VARCHAR(12) NOT NULL DEFAULT 'MEDIA',
    PRIMARY KEY (matricula_numero, ordem),
    CONSTRAINT proprietario_busca_confianca_valida
        CHECK (confianca IN ('ALTA', 'MEDIA', 'BAIXA'))
);

CREATE INDEX IF NOT EXISTS idx_busca_matricula_situacao
    ON matriculas_busca_aeri (situacao, numero DESC);
CREATE INDEX IF NOT EXISTS idx_busca_proprietario_nome
    ON proprietarios_matriculas_busca_aeri (nome_busca text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_busca_proprietario_documento
    ON proprietarios_matriculas_busca_aeri (documento_hash)
    WHERE documento_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS sincronizacao_matriculas_busca_aeri (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    limite_inicial INTEGER NOT NULL DEFAULT 39767,
    proximo_inicial INTEGER NOT NULL DEFAULT 1,
    ultimo_conhecido INTEGER NOT NULL DEFAULT 39767,
    proximo_revisao INTEGER NOT NULL DEFAULT 1,
    ultima_sincronizacao TIMESTAMPTZ,
    travado_em TIMESTAMPTZ,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO sincronizacao_matriculas_busca_aeri
    (id, limite_inicial, proximo_inicial, ultimo_conhecido, proximo_revisao)
VALUES (1, 39767, 1, 39767, 1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS matriculas_busca_erros_aeri (
    numero INTEGER PRIMARY KEY CHECK (numero > 0),
    modo VARCHAR(20) NOT NULL DEFAULT 'INICIAL',
    erro TEXT NOT NULL,
    tentativas INTEGER NOT NULL DEFAULT 1,
    primeira_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultima_tentativa_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_busca_matriculas_erros
    ON matriculas_busca_erros_aeri (ultima_tentativa_em ASC, numero ASC);
