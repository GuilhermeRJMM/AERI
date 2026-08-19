-- Habilita o PostGIS, se o servidor tiver, para calcular a área de
-- sobreposição entre polígonos.
--
-- Nada aqui pode levantar exceção. O executor de migrações roda dentro de
-- preparar_banco, que é dependência de todos os routers: uma migração que
-- falha não deixa o módulo Polígonos sem recurso, deixa o AERI inteiro
-- devolvendo 500. Por isso o CREATE EXTENSION vem dentro de um bloco com
-- tratamento de exceção, e todo o resto só é sequer compilado se a
-- extensão realmente existir.
DO $bloco$
BEGIN
    CREATE EXTENSION IF NOT EXISTS postgis;
EXCEPTION WHEN OTHERS THEN
    -- Servidor sem o pacote, ou usuário sem permissão para instalá-lo.
    -- Os dois são situações normais; o módulo continua respondendo quais
    -- polígonos se sobrepõem, apenas sem dizer quantos metros quadrados.
    RAISE NOTICE 'PostGIS indisponível (%). Sobreposição segue sem recorte.', SQLERRM;
END;
$bloco$;

-- A geometria NÃO é guardada em coluna. O anel em JSONB continua sendo a
-- única fonte da verdade, e o PostGIS entra como calculadora, não como
-- armazenamento. Guardar as duas formas criaria a chance de elas
-- divergirem -- e um polígono cuja geometria não corresponde ao anel que
-- o usuário desenhou é um erro que ninguém percebe olhando a tela.
DO $bloco$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        RETURN;
    END IF;

    -- EXECUTE (SQL dinâmico) de propósito: sem isso o PL/pgSQL tentaria
    -- validar os tipos do PostGIS ao compilar o bloco, e a migração
    -- quebraria justamente no servidor onde a extensão não existe.
    EXECUTE $funcao$
        CREATE OR REPLACE FUNCTION aeri_anel_para_geometria(anel jsonb)
        RETURNS geometry
        LANGUAGE sql
        IMMUTABLE
        RETURNS NULL ON NULL INPUT
        AS $corpo$
            SELECT ST_MakeValid(
                ST_SetSRID(
                    ST_GeomFromGeoJSON(
                        jsonb_build_object(
                            'type', 'Polygon',
                            -- O anel é gravado sem repetir o primeiro
                            -- ponto no fim; o PostGIS exige o anel
                            -- fechado, então ele é fechado aqui.
                            'coordinates', jsonb_build_array(
                                anel || jsonb_build_array(anel -> 0)
                            )
                        )::text
                    ),
                    4326
                )
            )
            WHERE jsonb_array_length(anel) >= 3
        $corpo$;
    $funcao$;
END;
$bloco$;
