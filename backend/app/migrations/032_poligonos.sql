-- Módulo Polígonos: desenho e conferência de perímetro sobre imagem de
-- satélite. Permissão própria, e não emprestada de pode_processar_matricula,
-- porque quem desenha limite de imóvel não é necessariamente quem analisa
-- matrícula -- e o contrário também vale.
ALTER TABLE usuarios_aeri
    ADD COLUMN IF NOT EXISTS pode_acessar_poligonos BOOLEAN NOT NULL DEFAULT FALSE;

-- Cargo administrativo já tem tudo; ninguém mais recebe por padrão, para o
-- acesso começar fechado e ser concedido caso a caso.
UPDATE usuarios_aeri
SET pode_acessar_poligonos=TRUE
WHERE perfil IN ('ADMIN', 'SUBSTITUTO');

-- Um desenho é sempre WGS84 (lon, lat) em graus decimais, no formato de anel
-- do GeoJSON: [[lon,lat], ...]. Guardar em graus decimais evita ter que
-- carregar o fuso UTM junto do dado; a conversão para UTM/GMS é feita na
-- exibição, que é onde o usuário escolhe como quer ler.
CREATE TABLE IF NOT EXISTS poligonos_aeri (
    id UUID PRIMARY KEY,
    nome TEXT NOT NULL,
    -- Vínculo opcional: um desenho pode existir antes de haver matrícula
    -- (estudo de desmembramento, conferência de memorial em qualificação).
    matricula INTEGER,
    tipo VARCHAR(12) NOT NULL DEFAULT 'POLIGONO',
    anel JSONB NOT NULL,
    -- Área e perímetro ficam materializados porque a listagem mostra os dois
    -- e recalcular a cada linha custaria uma varredura do anel inteiro.
    area_m2 DOUBLE PRECISION,
    perimetro_m DOUBLE PRECISION,
    cor VARCHAR(9) NOT NULL DEFAULT '#f97316',
    observacao TEXT,
    criado_por VARCHAR(40) REFERENCES usuarios_aeri(usuario),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT poligonos_tipo_valido CHECK (tipo IN ('POLIGONO', 'LINHA', 'PONTO'))
);

CREATE INDEX IF NOT EXISTS poligonos_aeri_matricula_idx
    ON poligonos_aeri (matricula) WHERE matricula IS NOT NULL;
CREATE INDEX IF NOT EXISTS poligonos_aeri_criado_em_idx
    ON poligonos_aeri (criado_em DESC);
