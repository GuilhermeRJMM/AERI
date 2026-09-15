from contextlib import ExitStack
from datetime import date
from unittest.mock import MagicMock, patch

from backend.app.servicos import buscas_movimentacoes as sinais
from backend.app.servicos import automacoes_operacionais as automatico


def conexao():
    con = MagicMock()
    con.__enter__.return_value = con
    cur = con.cursor.return_value.__enter__.return_value
    return con, cur


def test_descoberta_limitada_recupera_sete_dias_e_deduplica_protocolos():
    con, cur = conexao()
    cur.fetchone.return_value = {'id': 1}
    cliente = MagicMock()
    with patch.object(sinais, 'conectar', return_value=con), \
         patch.object(sinais, 'janelas_livro_protocolos', return_value=[('a','b'),('c','d'),('e','f')]), \
         patch.object(sinais, 'montar_protocolos_do_dia', return_value=[
             {'numero':'185.001','status':'REGISTRADO'},
             {'numero':'185.002','status':'PRENOTADO'},
         ]) as montar:
        assert sinais._descobrir_protocolos(cliente) == 1
    assert cliente.buscar_livro_protocolos.call_count == 3
    assert montar.call_count == 8
    insercoes = [c for c in cur.execute.call_args_list if 'INSERT INTO fila_protocolos' in c.args[0]]
    assert len(insercoes) == 1 and insercoes[0].args[1] == (185001,)


def test_descoberta_pausada_ou_em_intervalo_nao_consulta_api():
    con, cur = conexao()
    cur.fetchone.return_value = None
    cliente = MagicMock()
    with patch.object(sinais, 'conectar', return_value=con):
        assert sinais._descobrir_protocolos(cliente) == 0
    cliente.buscar_livro_protocolos.assert_not_called()


def test_falha_em_protocolo_reagenda_sem_descartar_os_demais():
    con, cur = conexao()
    cur.fetchall.return_value = [{'numero':185001},{'numero':185002}]
    cliente = MagicMock()
    cliente.buscar_protocolo_completo.side_effect = [RuntimeError('API'), {'itens':[]}]
    with patch.object(sinais, 'conectar', return_value=con), \
         patch.object(sinais, 'cliente_tri7', return_value=cliente), \
         patch.object(sinais, '_descobrir_protocolos'), \
         patch.object(sinais, 'registros_alterados_no_protocolo', return_value={('M',100),('RA',200)}), \
         patch.object(sinais, 'enfileirar_matriculas') as enfileirar:
        assert sinais.recuperar_movimentacoes() == 1
    enfileirar.assert_called_once_with(cur, {100}, 'MOVIMENTACAO_RECENTE')
    assert any('tentativas=tentativas+1' in c.args[0] for c in cur.execute.call_args_list)
    exclusoes = [c.args[1] for c in cur.execute.call_args_list if c.args[0].startswith('DELETE')]
    assert exclusoes == [(185002,)]


def test_livro_automatico_repassa_textos_ao_mesmo_indexador():
    con, cur = conexao()
    token = 'lease-teste'
    item = {'status':'REGISTRADO','conferido':True,'ocorrencias':[]}
    config = dict(habilitada=True, trava_ate=None, proxima_execucao=None, intervalo_minutos=30)
    trabalho = dict(id='execucao',data_alvo=date(2026,9,15),resultado={
        'fila':[item],'protocolos':[],'regrasHash':'versao'})
    cur.fetchone.side_effect = [config, trabalho, {'trava':token}]
    cliente = MagicMock()
    textos = {('M',100):('texto completo',None)}
    with ExitStack() as stack:
        stack.enter_context(patch.object(automatico,'conectar',return_value=con))
        stack.enter_context(patch.object(automatico,'uuid4',return_value=token))
        stack.enter_context(patch.object(automatico,'dentro_do_horario',return_value=True))
        stack.enter_context(patch.object(automatico,'hash_regras_livro_protocolos',return_value='versao'))
        stack.enter_context(patch.object(automatico,'cliente_tri7',return_value=cliente))
        stack.enter_context(patch.object(automatico,'excecoes_do_livro',return_value=frozenset()))
        stack.enter_context(patch.object(automatico,'conferir_itens_tri7',return_value=([item],{('M',100)},textos)))
        reindexar=stack.enter_context(patch.object(automatico,'reindexar_registros',return_value={'matriculas':1,'falhas':0}))
        resultado=automatico.executar_passo('livro_protocolos')
    assert resultado['estado']=='CONCLUIDO'
    reindexar.assert_called_once_with({('M',100)},textos,cliente)
    assert trabalho['resultado']['atualizacao']=={'matriculas':1,'falhas':0}
