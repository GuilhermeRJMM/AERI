ALTER TABLE sincronizacao_registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS travado_em TIMESTAMPTZ;
