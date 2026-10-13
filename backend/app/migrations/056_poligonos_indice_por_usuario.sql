-- As consultas operacionais de polígonos são sempre limitadas ao criador.
-- O campo obrigatório impede novos desenhos sem proprietário autenticado.
-- Não há registros existentes, então a restrição pode ser aplicada diretamente.
ALTER TABLE poligonos_aeri
    ALTER COLUMN criado_por SET NOT NULL;

-- O índice mantém a listagem por usuário rápida.
CREATE INDEX IF NOT EXISTS poligonos_aeri_usuario_criado_em_idx
    ON poligonos_aeri (criado_por, criado_em DESC);
