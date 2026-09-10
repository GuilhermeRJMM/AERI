-- Salão recreativo oculto: acesso adicional, presença efêmera e partidas privadas.
-- Nenhuma tabela abaixo participa dos fluxos registrais ou das permissões do AERI.
CREATE TABLE IF NOT EXISTS jogos_acessos_aeri (
    sessao_id UUID PRIMARY KEY REFERENCES sessoes_aeri(id) ON DELETE CASCADE,
    usuario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    autorizado_ate TIMESTAMPTZ NOT NULL,
    presente_ate TIMESTAMPTZ NOT NULL,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jogos_presenca
    ON jogos_acessos_aeri (presente_ate DESC);

CREATE TABLE IF NOT EXISTS jogos_tentativas_aeri (
    id BIGSERIAL PRIMARY KEY,
    sessao_id UUID NOT NULL REFERENCES sessoes_aeri(id) ON DELETE CASCADE,
    ip VARCHAR(64),
    sucesso BOOLEAN NOT NULL DEFAULT FALSE,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jogos_tentativas_recentes
    ON jogos_tentativas_aeri (sessao_id, criada_em DESC);

CREATE TABLE IF NOT EXISTS jogos_salas_aeri (
    id UUID PRIMARY KEY,
    nome VARCHAR(50) NOT NULL,
    senha_hash TEXT NOT NULL,
    criador VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    jogador_x VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    jogador_o VARCHAR(80) REFERENCES usuarios_aeri(usuario) ON DELETE SET NULL,
    tabuleiro JSONB NOT NULL DEFAULT '["", "", "", "", "", "", "", "", ""]'::jsonb,
    vez CHAR(1) NOT NULL DEFAULT 'X' CHECK (vez IN ('X', 'O')),
    vencedor VARCHAR(10),
    estado VARCHAR(20) NOT NULL DEFAULT 'AGUARDANDO'
        CHECK (estado IN ('AGUARDANDO', 'EM_JOGO', 'FINALIZADA', 'ABANDONADA')),
    versao INTEGER NOT NULL DEFAULT 1,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jogos_salas_ativas
    ON jogos_salas_aeri (atualizado_em DESC)
    WHERE estado IN ('AGUARDANDO', 'EM_JOGO');

CREATE TABLE IF NOT EXISTS jogos_convites_aeri (
    id UUID PRIMARY KEY,
    sala_id UUID NOT NULL REFERENCES jogos_salas_aeri(id) ON DELETE CASCADE,
    remetente VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    destinatario VARCHAR(80) NOT NULL REFERENCES usuarios_aeri(usuario) ON DELETE CASCADE,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDENTE'
        CHECK (estado IN ('PENDENTE', 'ACEITO', 'RECUSADO', 'EXPIRADO')),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '5 minutes'
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_jogos_convite_pendente
    ON jogos_convites_aeri (sala_id, destinatario)
    WHERE estado = 'PENDENTE';

CREATE INDEX IF NOT EXISTS idx_jogos_convites_destinatario
    ON jogos_convites_aeri (destinatario, estado, expira_em DESC);
