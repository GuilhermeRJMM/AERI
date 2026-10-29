from scripts.importar_intimacoes_relatorio import em_tratativa, em_tratativa_oficio, planejar_reconciliacao


def test_preserva_ausentes_sem_ignorar_encerramento_confirmado():
    relatorio = {
        'ativo': {'Status': 'Prenotado'},
        'novo': {'Status': 'Prenotado'},
        'concluido': {'Status': 'Desistência Concluída'},
        'entrega': {'Status': 'Entrega das importâncias recebidas'},
    }
    atuais = dict.fromkeys(['ativo', 'concluido', 'entrega', 'ausente'])
    plano = planejar_reconciliacao(relatorio, atuais, preservar_ausentes=True)
    assert plano['destino'] == {'ativo', 'novo', 'ausente'}
    assert plano['novos'] == ['novo']
    assert plano['remover'] == ['concluido', 'entrega']
    assert plano['preservados'] == ['ativo', 'ausente']
    assert plano['ausentes_preservados'] == ['ausente']


def test_sem_opcao_preserva_comportamento_anterior():
    plano = planejar_reconciliacao({'ativo': {'Status': 'Prenotado'}}, {'ativo': {}, 'ausente': {}})
    assert plano['destino'] == {'ativo'}
    assert plano['remover'] == ['ausente']
    assert plano['ausentes_preservados'] == []


def test_negativa_pagamento_e_desistencia_nao_comprovam_encerramento():
    assert em_tratativa('Negativa Pagamento')
    assert em_tratativa('Desistência')
    for status in ['Desistência Concluída', 'Entrega das importâncias recebidas', 'Arquivamento por desinteresse']:
        assert not em_tratativa(status)


def test_reconciliacao_repetida_nao_duplica_nem_remove_ausente_preservado():
    relatorio = {'ativo': {'Status': 'Prenotado'}}
    atuais = {'ativo': {}, 'ausente': {}}
    plano = planejar_reconciliacao(relatorio, atuais, preservar_ausentes=True)
    assert plano['novos'] == plano['remover'] == []
    assert plano['destino'] == set(atuais)


def test_plano_nao_altera_fontes_e_nao_escolhe_registros_por_contagem():
    relatorio = {'ativo': {'Status': 'Prenotado'}}
    atuais = {'ausente': {'nome_andamento': 'Conferir'}}
    plano = planejar_reconciliacao(relatorio, atuais, preservar_ausentes=True)
    assert plano['destino'] == {'ativo', 'ausente'}
    assert atuais == {'ausente': {'nome_andamento': 'Conferir'}}
    assert relatorio == {'ativo': {'Status': 'Prenotado'}}


def test_criterio_oficio_mantem_devolucao_pendente_e_exclui_negativa_pagamento():
    assert em_tratativa_oficio('Entrega das importâncias recebidas')
    assert em_tratativa_oficio('Desistência')
    assert not em_tratativa_oficio('Negativa Pagamento')
    assert not em_tratativa_oficio('Desistência Concluída')
    assert not em_tratativa_oficio('Arquivamento por desinteresse')


def test_restaura_sem_duplicar_e_separa_ausente_de_encerrado():
    relatorio = {'devolucao': {'Status': 'Entrega das importâncias recebidas'},
                 'negativa': {'Status': 'Negativa Pagamento'},
                 'novo': {'Status': 'Prenotado'}}
    plano = planejar_reconciliacao(relatorio, {'negativa': {}, 'ausente': {}},
                                  arquivadas={'devolucao': {}}, criterio_oficio=True)
    assert plano['destino'] == {'devolucao', 'novo'}
    assert plano['restaurar'] == ['devolucao']
    assert plano['novos'] == ['novo']
    assert plano['remover'] == ['ausente', 'negativa']


def test_criterio_oficio_idempotente():
    relatorio = {'devolucao': {'Status': 'Entrega das importâncias recebidas'},
                 'negativa': {'Status': 'Negativa Pagamento'}}
    plano = planejar_reconciliacao(relatorio, {'devolucao': {}},
                                  arquivadas={'negativa': {}}, criterio_oficio=True)
    assert plano['destino'] == {'devolucao'}
    assert plano['restaurar'] == plano['novos'] == plano['remover'] == []
