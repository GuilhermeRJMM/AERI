ALTER TABLE sessoes_aeri
    ADD COLUMN IF NOT EXISTS origem_autenticacao VARCHAR(10) NOT NULL DEFAULT 'LOCAL'
    CHECK (origem_autenticacao IN ('LOCAL', 'HUB'));

-- O login HUB e sua sessão foram criados na mesma transação (NOW igual).
-- Não inferir origem pelo cargo, nome, user-agent ou existência de vínculo.
UPDATE sessoes_aeri s SET origem_autenticacao='HUB'
WHERE s.origem_autenticacao='LOCAL' AND EXISTS (
    SELECT 1 FROM auditoria_aeri a
    WHERE a.acao='login_hub' AND a.resultado='sucesso'
      AND a.usuario=s.usuario AND a.criada_em=s.criada_em
);
