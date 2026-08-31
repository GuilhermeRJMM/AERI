CREATE TABLE IF NOT EXISTS contratos_trabalhos_aeri (
 id UUID PRIMARY KEY,
 usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario),
 protocolo VARCHAR(30) NOT NULL,
 documento_id VARCHAR(30) NOT NULL,
 estado VARCHAR(30) NOT NULL DEFAULT 'AGUARDANDO',
 versao INTEGER NOT NULL DEFAULT 1,
 progresso INTEGER NOT NULL DEFAULT 0,
 payload_cifrado TEXT,
 erro VARCHAR(250),
 trava UUID,
 trava_ate TIMESTAMPTZ,
 criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_contratos_pendentes ON contratos_trabalhos_aeri(usuario,protocolo,documento_id)
WHERE estado IN ('AGUARDANDO','PROCESSANDO');
CREATE INDEX IF NOT EXISTS idx_contratos_fila ON contratos_trabalhos_aeri(estado,criado_em);
CREATE TABLE IF NOT EXISTS contratos_versoes_aeri (
 id BIGSERIAL PRIMARY KEY,
 trabalho_id UUID NOT NULL REFERENCES contratos_trabalhos_aeri(id) ON DELETE CASCADE,
 versao INTEGER NOT NULL,
 usuario VARCHAR(80) REFERENCES usuarios_aeri(usuario),
 etapa VARCHAR(40) NOT NULL,
 payload_cifrado TEXT NOT NULL,
 criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(trabalho_id,versao)
);
