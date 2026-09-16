"""Atualização do índice compartilhada pelo Livro manual e automático."""
from backend.app.database import conectar
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.buscas_mencoes import enfileirar_matriculas
from backend.app.servicos.custas import revalidar_negativas_custas


def reindexar_registros(alterados, cache_textos, cliente, request=None, usuario='executor',
                       salvar_matricula=None, salvar_auxiliar=None):
    if salvar_matricula is None:
        from backend.app.rotas.buscas_indexacao import _salvar_indice
        salvar_matricula = _salvar_indice
    if salvar_auxiliar is None:
        from backend.app.rotas.registros_auxiliares import _salvar_indice
        salvar_auxiliar = _salvar_indice
    relatorio = dict(matriculas=0, matriculasNovas=0, matriculasAlteradas=0,
        registrosAuxiliares=0, registrosAuxiliaresNovos=0,
        custasRevalidadas=0, falhas=0, numerosComFalha=[])
    if not alterados:
        return relatorio
    with conectar() as con:
        with con.cursor() as cur:
            for tipo, numero in sorted(alterados):
                try:
                    # Savepoint: erro de uma matrícula não invalida as demais.
                    with con.transaction():
                        texto = (cache_textos.get((tipo, numero)) or (None, None))[0]
                        if texto is None:
                            consulta = cliente.buscar_texto_matricula if tipo == 'M' else cliente.buscar_texto_registro_auxiliar
                            texto = consulta(numero)['texto']
                        if tipo == 'M':
                            _, novo, alterado, _, _ = salvar_matricula(cur, numero, texto)
                            relatorio['matriculas'] += 1
                            relatorio['matriculasNovas'] += int(novo)
                            relatorio['matriculasAlteradas'] += int(alterado)
                            cur.execute('''UPDATE sincronizacao_matriculas_busca_aeri
                                SET ultimo_conhecido=GREATEST(ultimo_conhecido,%s) WHERE id=1''', (numero,))
                        else:
                            _, novo = salvar_auxiliar(cur, numero, texto)
                            relatorio['registrosAuxiliares'] += 1
                            relatorio['registrosAuxiliaresNovos'] += int(novo)
                except Exception:
                    relatorio['falhas'] += 1
                    if len(relatorio['numerosComFalha']) < 20:
                        relatorio['numerosComFalha'].append(f'{tipo}.{numero}')
                    if tipo == 'M':
                        enfileirar_matriculas(cur, [numero], 'LIVRO_PROTOCOLOS')

            # O Livro de Protocolos tambem alimenta o indice do Registro
            # Auxiliar. Assim que um desses textos entra (novo ou alterado),
            # uma negativa antiga do Informar Custas pode deixar de ser
            # verdadeira. Revalidamos ainda na mesma operacao, sem depender
            # do proximo ciclo do executor ou de uma nova busca manual.
            if relatorio['registrosAuxiliares']:
                try:
                    with con.transaction():
                        corrigidos = revalidar_negativas_custas(
                            cur, usuario, limite=1000
                        )
                    relatorio['custasRevalidadas'] = len(corrigidos)
                except Exception:
                    # A conferencia do Livro continua valida, mas a falha fica
                    # explicita na auditoria e na resposta para nova tentativa.
                    relatorio['falhas'] += 1
                    if len(relatorio['numerosComFalha']) < 20:
                        relatorio['numerosComFalha'].append('CUSTAS.REVALIDACAO')
            registrar_auditoria_cursor(cur, request, 'reindexar_pelo_livro_protocolos',
                'parcial' if relatorio['falhas'] else 'sucesso', usuario, detalhes=relatorio)
        con.commit()
    return relatorio
