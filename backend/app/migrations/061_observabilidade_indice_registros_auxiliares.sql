-- A carga inicial não informa quando novos números e lacunas foram conferidos.
-- Os marcadores só avançam depois de um lote sem falhas técnicas.
ALTER TABLE sincronizacao_registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS ultima_sondagem_novos_em TIMESTAMPTZ;
ALTER TABLE sincronizacao_registros_auxiliares_aeri
    ADD COLUMN IF NOT EXISTS ultima_varredura_lacunas_em TIMESTAMPTZ;
