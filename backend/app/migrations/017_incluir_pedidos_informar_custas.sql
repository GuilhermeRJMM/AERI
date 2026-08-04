WITH dados (
    pedido, nome, documento, modalidade, produto, safra, resultado, numero_registro
) AS (
    VALUES
        ('S26071061901D', 'RAFAEL BORGES MARTINS', '017.597.481-02', 'PENHOR', 'SOJA', '2026/2027', 'POSITIVA', '29.379'),
        ('S26071061949D', 'RAFAEL BORGES MARTINS', '017.597.481-02', 'ALIENACAO_FIDUCIARIA', 'SOJA', '2026/2027', 'NEGATIVA', ''),
        ('S26071062129D', 'FRANCISCO MARTINS DA SILVA', '049.318.901-72', 'PENHOR', 'SOJA', '2026/2027', 'NEGATIVA', ''),
        ('S26071062192D', 'FRANCISCO MARTINS DA SILVA', '049.318.901-72', 'ALIENACAO_FIDUCIARIA', 'SOJA', '2026/2027', 'NEGATIVA', ''),
        ('S26071062350D', 'MARCILAINE JORGE DE LIMA', '022.388.651-36', 'PENHOR', 'SOJA', '2026/2027', 'NEGATIVA', ''),
        ('S26071062405D', 'MARCILAINE JORGE DE LIMA', '022.388.651-36', 'ALIENACAO_FIDUCIARIA', 'SOJA', '2026/2027', 'NEGATIVA', ''),
        ('S26080005877D', 'PAULO CESAR CHIARI', '028.080.828-35', 'PENHOR', 'SOJA', '2026/2027', 'NEGATIVA', ''),
        ('S26080005946D', 'PAULO CESAR CHIARI', '028.080.828-35', 'ALIENACAO_FIDUCIARIA', 'SOJA', '2026/2027', 'POSITIVA', '29.389, 29.461 e 29.469')
), incluidos AS (
    INSERT INTO custas_livro3_aeri (
        id, pedido, nome, documento, modalidade, produto, safra,
        resultado, numero_registro, status, finalizado
    )
    SELECT
        gen_random_uuid(), pedido, nome, documento, modalidade, produto, safra,
        resultado, numero_registro, 'CUSTAS_INFORMADAS', FALSE
    FROM dados
    ON CONFLICT (pedido) DO UPDATE SET
        nome=EXCLUDED.nome,
        documento=EXCLUDED.documento,
        modalidade=EXCLUDED.modalidade,
        produto=EXCLUDED.produto,
        safra=EXCLUDED.safra,
        resultado=EXCLUDED.resultado,
        numero_registro=EXCLUDED.numero_registro,
        status='CUSTAS_INFORMADAS',
        finalizado=FALSE,
        finalizado_em=NULL,
        atualizado_em=NOW()
    RETURNING id, pedido
)
INSERT INTO eventos_custas_livro3_aeri (item_id, pedido, tipo, detalhes)
SELECT id, pedido, 'IMPORTACAO_MANUAL', '{"origem":"solicitacao_operacional"}'::jsonb
FROM incluidos;
