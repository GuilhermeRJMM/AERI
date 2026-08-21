-- Base jurídica rastreável para a revisão assistida por IA.
-- O texto integral das matrículas nunca é persistido nestas tabelas.
CREATE TABLE IF NOT EXISTS fontes_juridicas_aeri (
    id UUID PRIMARY KEY,
    titulo TEXT NOT NULL,
    nome_arquivo TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL UNIQUE,
    tipo_documento VARCHAR(12) NOT NULL,
    jurisdicao VARCHAR(40) NOT NULL DEFAULT 'NAO_INFORMADA',
    autoridade VARCHAR(160) NOT NULL DEFAULT '',
    referencia_normativa VARCHAR(200) NOT NULL DEFAULT '',
    classe_fonte VARCHAR(20) NOT NULL DEFAULT 'APOIO',
    url_oficial TEXT NOT NULL DEFAULT '',
    total_paginas INTEGER NOT NULL DEFAULT 0,
    total_trechos INTEGER NOT NULL DEFAULT 0,
    texto_extraido BOOLEAN NOT NULL DEFAULT TRUE,
    qualidade_extracao VARCHAR(20) NOT NULL DEFAULT 'BOA',
    vigente BOOLEAN NOT NULL DEFAULT TRUE,
    criado_por VARCHAR(80) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fonte_juridica_tipo_valido CHECK (tipo_documento IN ('PDF','DOCX','TXT')),
    CONSTRAINT fonte_juridica_classe_valida CHECK (
        classe_fonte IN ('PRIMARIA','ORIENTACAO','APOIO','DOUTRINA')
    ),
    CONSTRAINT fonte_juridica_paginas_validas CHECK (total_paginas >= 0),
    CONSTRAINT fonte_juridica_trechos_validos CHECK (total_trechos >= 0),
    CONSTRAINT fonte_juridica_qualidade_valida CHECK (
        qualidade_extracao IN ('BOA','PARCIAL','INSUFICIENTE')
    )
);

CREATE TABLE IF NOT EXISTS trechos_juridicos_aeri (
    id BIGSERIAL PRIMARY KEY,
    fonte_id UUID NOT NULL REFERENCES fontes_juridicas_aeri(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    pagina_inicial INTEGER,
    pagina_final INTEGER,
    referencia TEXT NOT NULL DEFAULT '',
    texto TEXT NOT NULL,
    busca TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('portuguese', coalesce(referencia, '') || ' ' || texto)
    ) STORED,
    UNIQUE (fonte_id, ordem),
    CONSTRAINT trecho_juridico_ordem_valida CHECK (ordem >= 0),
    CONSTRAINT trecho_juridico_texto_valido CHECK (length(texto) BETWEEN 20 AND 12000)
);

CREATE INDEX IF NOT EXISTS idx_trechos_juridicos_busca
    ON trechos_juridicos_aeri USING GIN (busca);
CREATE INDEX IF NOT EXISTS idx_fontes_juridicas_vigentes
    ON fontes_juridicas_aeri (vigente, jurisdicao, atualizado_em DESC);

CREATE TABLE IF NOT EXISTS analises_juridicas_aeri (
    id UUID PRIMARY KEY,
    matricula_numero INTEGER NOT NULL,
    resultado_hash CHAR(64) NOT NULL,
    base_hash CHAR(64) NOT NULL,
    modelo VARCHAR(100) NOT NULL,
    conclusao VARCHAR(20) NOT NULL,
    confianca VARCHAR(10) NOT NULL,
    parecer JSONB NOT NULL,
    fontes JSONB NOT NULL DEFAULT '[]'::jsonb,
    unidades_entrada INTEGER NOT NULL DEFAULT 0,
    unidades_saida INTEGER NOT NULL DEFAULT 0,
    criado_por VARCHAR(80) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analise_juridica_conclusao_valida CHECK (
        conclusao IN ('ANALISE_CONCLUIDA','ATENCAO','INCONCLUSIVO')
    ),
    CONSTRAINT analise_juridica_confianca_valida CHECK (
        confianca IN ('ALTA','MEDIA','BAIXA')
    ),
    UNIQUE (matricula_numero, resultado_hash, base_hash)
);

CREATE INDEX IF NOT EXISTS idx_analises_juridicas_limite_diario
    ON analises_juridicas_aeri (criado_em DESC);
