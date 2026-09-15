"""Pesquisa combinada: titularidade atual e menções históricas separadas."""
from datetime import datetime, timezone
from math import ceil

from fastapi import HTTPException

from backend.app.servicos.buscas import hash_documento, normalizar_documento, normalizar_nome


def filtros_identidade(nome, documento, alias='p', exata=False):
    nome = normalizar_nome(nome)
    documento = normalizar_documento(documento)
    if documento and len(documento) not in {11, 14}:
        raise HTTPException(422, 'Informe o CPF ou CNPJ completo.')
    if not documento and len(nome) < 3:
        raise HTTPException(422, 'Informe ao menos três caracteres do nome ou o CPF/CNPJ completo.')
    partes, parametros = [], []
    try:
        if documento:
            partes.append(f'{alias}.documento_hash=%s')
            parametros.append(hash_documento(documento))
    except RuntimeError as exc:
        raise HTTPException(503, 'A busca por documento está indisponível nesta configuração.') from exc
    if len(nome) >= 3:
        # Palavras fora de ordem são candidatos, não identidade confirmada.
        tokens = [t for t in nome.split() if t not in {'DA','DE','DO','DAS','DOS','E'}]
        condicao = f'{alias}.nome_busca=%s' if exata or not tokens else ' AND '.join(f'{alias}.nome_busca LIKE %s' for _ in tokens)
        valores = [nome] if exata or not tokens else [f'%{t}%' for t in tokens]
        partes.append(f'({condicao})')
        parametros.extend(valores)
    return '(' + ' OR '.join(partes) + ')', parametros, nome, documento


def _item(row, nome, documento_protegido):
    doc_igual = bool(documento_protegido and row.get('documento_hash') == documento_protegido)
    conflito = bool(documento_protegido and row.get('documento_hash') and not doc_igual)
    correspondencia = ('DOCUMENTO_DIVERGENTE' if conflito else 'DOCUMENTO_EXATO' if doc_igual
        else 'NOME_EXATO_SEM_DOCUMENTO' if documento_protegido and row['nome_busca'] == nome
        else 'NOME_EXATO' if row['nome_busca'] == nome else 'VARIACAO_DE_NOME')
    pendente = bool(row.get('falha_consulta_em') or row.get('veredito_cadeia') != 'OK'
        or row.get('indice_busca_versao', 0) < 2 or conflito
        or documento_protegido and not doc_igual)
    return dict(matricula=row['numero'], nome=row['nome'], documento=row['documento_mascarado'],
        tipoDocumento=row['tipo_documento'], proporcao=row['proporcao'], origem=row['origem'],
        situacao=row['situacao'], confianca='BAIXA' if pendente else row['confianca'],
        correspondencia=correspondencia, revisaoPendente=pendente,
        consultadoEm=row['consultado_em'].isoformat())


def pesquisar(cursor, nome='', documento='', pagina=1, limite=50, somente_ativos=True, exportar=False):
    filtro, parametros, nome, documento = filtros_identidade(nome, documento, exata=exportar)
    protegido = hash_documento(documento) if documento else None
    if documento:
        cursor.execute('''SELECT COUNT(*) AS total FROM matriculas_busca_aeri
            WHERE texto_hash IS NOT NULL AND documentos_hash_versao IS DISTINCT FROM 1''')
        if cursor.fetchone()['total']:
            raise HTTPException(503, 'A busca por CPF/CNPJ aguarda a reindexação segura dos documentos.')
    # Alias comprovado pelo mesmo documento dentro da mesma matrícula.
    # Documento antigo retificado nunca é promovido ao documento atual.
    if nome:
        filtro = f'''({filtro} OR EXISTS (SELECT 1 FROM mencoes_matriculas_busca_aeri x
            WHERE x.matricula_numero=p.matricula_numero AND x.documento_hash=p.documento_hash
              AND x.nome_busca=%s))'''
        parametros.append(nome)
    estado = "AND m.situacao='ATIVA'" if somente_ativos or exportar else ''
    base = f'''FROM proprietarios_matriculas_busca_aeri p
        JOIN matriculas_busca_aeri m ON m.numero=p.matricula_numero
        LEFT JOIN auditorias_matriculas_aeri a ON a.matricula_numero=m.numero
        WHERE {filtro} {estado}'''
    cursor.execute(f'SELECT COUNT(*) AS total,COUNT(DISTINCT m.numero) AS matriculas {base}', tuple(parametros))
    contagem = cursor.fetchone()
    total = int(contagem['total'])
    if exportar and total > 5000:
        raise HTTPException(422, 'Refine a pesquisa pelo CPF/CNPJ antes de exportar.')
    tamanho = 5000 if exportar else limite
    cursor.execute(f'''SELECT m.numero,m.situacao,m.consultado_em,m.falha_consulta_em,m.indice_busca_versao,
        p.nome,p.nome_busca,p.documento_hash,p.documento_mascarado,p.tipo_documento,p.proporcao,p.origem,
        p.confianca,a.veredito_cadeia {base}
        ORDER BY CASE WHEN p.documento_hash=%s THEN 0 WHEN p.nome_busca=%s THEN 1 ELSE 2 END,
        p.nome,m.numero,p.ordem LIMIT %s OFFSET %s''', (*parametros, protegido, nome, tamanho, (pagina-1)*limite if not exportar else 0))
    itens = [_item(row, nome, protegido) for row in cursor.fetchall()]

    filtro_m, param_m, _, _ = filtros_identidade(nome, documento, 'x', exata=exportar)
    cursor.execute(f'''SELECT m.numero,m.situacao,m.consultado_em,
        bool_or(m.quantidade_proprietarios=0 OR COALESCE(a.veredito_cadeia,'REVISAR')<>'OK'
                OR m.falha_consulta_em IS NOT NULL) AS revisar,
        jsonb_agg(DISTINCT jsonb_build_object('nome',x.nome,'ato',x.ato,'papel',x.papel)) AS mencoes
        FROM mencoes_matriculas_busca_aeri x JOIN matriculas_busca_aeri m ON m.numero=x.matricula_numero
        LEFT JOIN auditorias_matriculas_aeri a ON a.matricula_numero=m.numero
        WHERE {filtro_m} {estado}
          AND NOT EXISTS(SELECT 1 FROM proprietarios_matriculas_busca_aeri p
            WHERE p.matricula_numero=x.matricula_numero
            AND (p.nome_busca=x.nome_busca OR p.documento_hash=x.documento_hash))
        GROUP BY m.numero,m.situacao,m.consultado_em
        ORDER BY revisar DESC,m.numero LIMIT 51''', tuple(param_m))
    encontrados = cursor.fetchall()
    candidatos = [dict(matricula=r['numero'], situacao=r['situacao'], revisaoPendente=r['revisar'],
        consultadoEm=r['consultado_em'].isoformat(), mencoes=r['mencoes']) for r in encontrados[:50]]
    if exportar:
        # CPF prevalece; nomes correspondentes sem documento exigem identificação.
        if protegido:
            itens = [i for i in itens if i['correspondencia'] not in {'DOCUMENTO_DIVERGENTE'}]
        if any(i['revisaoPendente'] for i in itens) or any(c['revisaoPendente'] for c in candidatos) or len(encontrados)>50:
            raise HTTPException(409, 'Há correspondências que precisam de conferência. Revise a identificação e as matrículas indicadas antes de gerar o texto.')
    cursor.execute('''SELECT COUNT(*) FILTER(WHERE situacao='ATIVA' AND quantidade_proprietarios=0) AS sem_titular,
        COUNT(*) FILTER(WHERE texto_hash IS NOT NULL AND indice_busca_versao<2) AS mencoes_pendentes,
        MIN(consultado_em) FILTER(WHERE situacao='ATIVA') AS mais_antiga
        FROM matriculas_busca_aeri''')
    cobertura = dict(cursor.fetchone())
    cobertura['mais_antiga'] = cobertura['mais_antiga'].isoformat() if cobertura.get('mais_antiga') else None
    if exportar and not itens and (cobertura['mencoes_pendentes'] or cobertura['sem_titular']):
        raise HTTPException(409, 'Nenhum titular localizado, mas o índice ainda possui lacunas de extração. Conclua a conferência antes de gerar uma negativa.')
    return dict(termo=nome or documento, nomePesquisa=nome, tipoBusca='COMBINADA' if nome and documento else 'NOME' if nome else 'DOCUMENTO_EXATO',
        quantidade=len(itens), total=total, totalMatriculas=contagem['matriculas'], pagina=pagina, porPagina=limite,
        totalPaginas=ceil(total/limite), itens=itens, candidatos=candidatos, maisCandidatos=len(encontrados)>50,
        cobertura=cobertura, consultadaEm=datetime.now(timezone.utc).isoformat())
