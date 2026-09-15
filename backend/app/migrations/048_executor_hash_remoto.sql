-- Credencial exclusiva de máquina. Nunca armazena a chave HMAC do índice.
CREATE TABLE IF NOT EXISTS executores_hash_documentos_aeri (
 id UUID PRIMARY KEY,
 nome VARCHAR(100) NOT NULL,
 token_hash CHAR(64) NOT NULL UNIQUE,
 criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 expira_em TIMESTAMPTZ NOT NULL,
 revogado_em TIMESTAMPTZ,
 ultima_chamada_em TIMESTAMPTZ,
 janela_em TIMESTAMPTZ,
 chamadas_janela INTEGER NOT NULL DEFAULT 0,
 documentos_janela INTEGER NOT NULL DEFAULT 0
);
