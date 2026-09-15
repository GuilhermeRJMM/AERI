"""Pessoas por ato para recuperação de candidatos, sem atribuir titularidade.

Texto integral e documentos abertos não são persistidos. As menções servem
para localizar a matrícula e identificar o papel em que a pessoa apareceu.
"""
from backend.app.proprietarios import (
    extrair_bloco, extrair_pessoas, extrair_proprietario_inicial,
    extrair_retificacoes_cpf,
)
from backend.app.parser import separar_atos
from backend.app.servicos.buscas import (
    hash_documento, mascarar_documento, normalizar_nome, tipo_documento,
)

INDICE_BUSCA_VERSAO = 2


def extrair_mencoes(texto, resultado):
    mencoes = {}

    def adicionar(ato, papel, pessoas):
        for pessoa in pessoas:
            nome = str(pessoa.get('nome') or '').strip()[:300]
            normalizado = normalizar_nome(nome)
            if len(normalizado) < 3:
                continue
            documento = pessoa.get('cpf') or ''
            protegido = hash_documento(documento) or None
            chave = (ato, papel, normalizado, protegido)
            mencoes[chave] = dict(ato=ato[:40], papel=papel, nome=nome,
                nome_busca=normalizado, documento_hash=protegido,
                documento_mascarado=mascarar_documento(documento),
                tipo_documento=tipo_documento(documento))

    atos = separar_atos(texto)
    inicio = texto.find(atos[0]['texto']) if atos else -1
    cabecalho = texto[:inicio] if inicio >= 0 else texto if not atos else ''
    adicionar('ABERTURA', 'PROPRIETARIO_INICIAL', extrair_proprietario_inicial(cabecalho))
    for ato in atos:
        codigo = str(ato.get('codigo') or '')
        descricao = str(ato.get('texto') or '')
        for tipo, papel in (('ADQUIRENTE', 'ADQUIRENTE'), ('TRANSMITENTE', 'TRANSMITENTE')):
            adicionar(codigo, papel, extrair_pessoas(extrair_bloco(descricao, tipo)))
        adicionar(codigo, 'RETIFICACAO', extrair_retificacoes_cpf(descricao))
        # Qualificados são candidatos históricos, incluindo intervenientes.
        # Jamais entram na tabela de proprietários por esta extração.
        adicionar(codigo, 'QUALIFICADO', extrair_pessoas(descricao))
    return list(mencoes.values())


def salvar_mencoes(cursor, numero, texto, resultado):
    mencoes = extrair_mencoes(texto, resultado)
    cursor.execute('DELETE FROM mencoes_matriculas_busca_aeri WHERE matricula_numero=%s', (numero,))
    for m in mencoes:
        cursor.execute('''INSERT INTO mencoes_matriculas_busca_aeri
            (matricula_numero,ato,papel,nome,nome_busca,documento_hash,documento_mascarado,tipo_documento)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
            (numero, m['ato'], m['papel'], m['nome'], m['nome_busca'],
             m['documento_hash'], m['documento_mascarado'], m['tipo_documento']))


def enfileirar_matriculas(cursor, numeros, motivo):
    for numero in sorted(set(n for n in numeros if isinstance(n, int) and n > 0)):
        cursor.execute('''INSERT INTO fila_matriculas_busca_aeri(numero,motivo)
            VALUES (%s,%s) ON CONFLICT(numero) DO UPDATE SET
            motivo=EXCLUDED.motivo,solicitada_em=NOW()''', (numero, motivo[:40]))
