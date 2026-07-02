ALTER TABLE intimacoes_aeri
    ADD COLUMN IF NOT EXISTS nome_andamento VARCHAR(160) NOT NULL DEFAULT 'Não informado';

-- Cópia de segurança anterior à importação do relatório de 01/07/2026.
CREATE TABLE IF NOT EXISTS backup_intimacoes_20260702_antes_importacao
    AS TABLE intimacoes_aeri;

WITH relatorio (protocolo, credor, nome_andamento, ultimo_andamento) AS (
    VALUES
        ('IN00797637C', 'CAIXA ECONÔMICA FEDERAL', 'Arquivamento por desinteresse', DATE '2022-11-22'),
        ('IN01345616C', 'CAIXA ECONÔMICA FEDERAL', 'Negativa Pagamento', DATE '2026-06-23'),
        ('IN01394314C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-04-07'),
        ('IN01473689C', 'CAIXA ECONÔMICA FEDERAL', 'Negativa Pagamento', DATE '2026-06-05'),
        ('IN01547166C', 'COOPERATIVA DE CREDITO DE LIVRE ADMISSAO DO CENTRO-SUL GOIANO LTDA', 'Desistência', DATE '2026-06-08'),
        ('IN01605587C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-12'),
        ('IN01608295C', 'COOPERATIVA DE CREDITO DE LIVRE ADMISSAO DO CENTRO-SUL GOIANO LTDA', 'Expedição de Intimação - RI', DATE '2026-06-30'),
        ('IN00781194C', 'CAIXA ECONÔMICA FEDERAL', 'Arquivamento por desinteresse', DATE '2023-04-28'),
        ('IN00781201C', 'CAIXA ECONÔMICA FEDERAL', 'Arquivamento por desinteresse', DATE '2022-11-22'),
        ('IN01321817C', 'CAIXA ECONÔMICA FEDERAL', 'Arquivamento por desinteresse', DATE '2025-02-27'),
        ('IN01430613C', 'CAIXA ECONÔMICA FEDERAL', 'Negativa Pagamento', DATE '2026-06-05'),
        ('IN01460329C', 'Crespo e Caires Advogados Associados', 'Devolvido com Exigências', DATE '2026-05-28'),
        ('IN01469235C', 'CAIXA ECONÔMICA FEDERAL', 'Negativa Pagamento', DATE '2025-12-29'),
        ('IN01504624C', 'Marcus Junqueira e Paulo Junqueira Sociedade de Advogados', 'Pagamento Efetuado', DATE '2026-06-11'),
        ('IN01625306C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-30'),
        ('IN01381247C', 'CAIXA ECONÔMICA FEDERAL', 'Prenotado', DATE '2026-06-18'),
        ('IN01515397C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-02-05'),
        ('IN01595081C', 'Melaragno Monteiro e Advogados Associados', 'Expedição de Intimação - RI', DATE '2026-06-25'),
        ('IN01598693C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-24'),
        ('IN01581267C', 'CAIXA ECONÔMICA FEDERAL', 'Não Intimado', DATE '2026-07-01'),
        ('IN01592272C', 'SANTYAGO REZENDE - SOCIEDADE INDIVIDUAL DE ADVOCACIA', 'Devolvido com Exigências', DATE '2026-06-08'),
        ('IN01322991C', 'CAIXA ECONÔMICA FEDERAL', 'Arquivamento por desinteresse', DATE '2025-02-28'),
        ('IN01574996C', 'AK Cobranças Ltda.', 'Expedição de Intimação - RI', DATE '2026-06-18'),
        ('IN01620856C', 'Hispagnol e Rosa Sociedade de Advogados', 'Expedição de Intimação - RI', DATE '2026-06-17'),
        ('IN01369960C', 'CAIXA ECONÔMICA FEDERAL', 'Cumprindo Exigência', DATE '2026-06-25'),
        ('IN01506704C', 'CLS Organização e Administração de Documentos LTDA', 'Desistência', DATE '2026-06-09'),
        ('IN01531518C', 'Portal de Documentos S/A.', 'Intimação por Edital', DATE '2026-06-17'),
        ('IN01565781C', 'CAIXA ECONÔMICA FEDERAL', 'Desistência', DATE '2026-06-29'),
        ('IN01625860C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-24'),
        ('IN01621775C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-18'),
        ('IN01401145C', 'CAIXA ECONÔMICA FEDERAL', 'Cumprindo Exigência', DATE '2026-06-19'),
        ('IN01569459C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-03'),
        ('IN01581041C', 'COOPERATIVA DE CREDITO DE LIVRE ADMISSAO DO CENTRO-SUL GOIANO LTDA', 'Não Intimado', DATE '2026-07-01'),
        ('IN01358054C', 'CAIXA ECONÔMICA FEDERAL', 'Cumprindo Exigência', DATE '2026-06-17'),
        ('IN01391476C', 'CAIXA ECONÔMICA FEDERAL', 'Negativa Pagamento', DATE '2026-06-05'),
        ('IN01422847C', 'CAIXA ECONÔMICA FEDERAL', 'Negativa Pagamento', DATE '2026-06-05'),
        ('IN01503150C', 'CLS Organização e Administração de Documentos LTDA', 'Projeção Atualizada', DATE '2026-06-30'),
        ('IN01581064C', 'AK Cobranças Ltda.', 'Expedição de Intimação - RI', DATE '2026-06-16'),
        ('IN01614439C', 'CAIXA ECONÔMICA FEDERAL', 'Expedição de Intimação - RI', DATE '2026-06-24')
)
INSERT INTO intimacoes_aeri (
    id, protocolo, credor, devedor, nome_andamento, ultimo_andamento
)
SELECT
    md5('aeri:' || protocolo)::uuid,
    protocolo,
    credor,
    'Não informado no relatório',
    nome_andamento,
    ultimo_andamento
FROM relatorio
ON CONFLICT (protocolo) DO UPDATE SET
    credor = EXCLUDED.credor,
    nome_andamento = EXCLUDED.nome_andamento,
    ultimo_andamento = EXCLUDED.ultimo_andamento,
    atualizado_em = NOW();
