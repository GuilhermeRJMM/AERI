"""Teste opt-in em tabelas TEMPORÁRIAS; não lê nem altera intimações reais."""
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from backend.app.servicos import rtd_sincronizacao as sync


@unittest.skipUnless(os.getenv('AERI_TEST_RTD_DB') == '1', 'Requer Postgres para tabelas temporárias')
class TesteRtdPostgres(unittest.TestCase):
    def test_fila_vinculos_eventos_e_leitura_concorrente(self):
        import psycopg
        from psycopg.rows import dict_row
        from backend.app.database import database_url
        from backend.app.rotas.rtd_intimacoes import marcar_lido, Leitura
        from psycopg.conninfo import conninfo_to_dict
        parametros = conninfo_to_dict(database_url())
        if '-pooler' in parametros.get('host', ''):
            parametros['host'] = parametros['host'].replace('-pooler', '')
        # Não usar pool transacional: tabelas temporárias exigem sessão dedicada.
        with psycopg.connect(**parametros, row_factory=dict_row) as con:
            with con.cursor() as c:
                c.execute('CREATE TEMP TABLE usuarios_aeri(usuario VARCHAR(80) PRIMARY KEY)')
                c.execute('''CREATE TEMP TABLE intimacoes_aeri(id UUID PRIMARY KEY,protocolo TEXT,
                    protocolo_rtd TEXT,excluida_em TIMESTAMPTZ,devedor TEXT,
                    devedor_rtd_valor TEXT,atualizado_em TIMESTAMPTZ)''')
                sql = (Path(__file__).parents[1] / 'backend/app/migrations/050_rtd_intimacoes.sql').read_text(encoding='utf8')
                c.execute(sql.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
                c.execute('ALTER TABLE rtd_pedidos_aeri ADD COLUMN destinatarios JSONB DEFAULT \'[]\'::jsonb')
                # Confirma que toda escrita do teste está isolada em pg_temp.
                c.execute("SELECT relpersistence FROM pg_class WHERE oid='rtd_pedidos_aeri'::regclass")
                self.assertEqual(c.fetchone()['relpersistence'], 't')
                alvo = uuid4()
                c.execute("INSERT INTO usuarios_aeri VALUES ('teste1'),('teste2')")
                c.execute('INSERT INTO intimacoes_aeri(id,protocolo) VALUES (%s,%s)',(alvo,'IN01669965C'))
            con.commit()

            @contextmanager
            def conectar_teste():
                yield con

            p1, p2 = '20260924145692380', '20260924145692381'
            cliente = Mock()
            def dados(p):
                return {'Protocolo':p, 'Situacao':'Orçamento',
                        'UrlArquivoEnviado':'https://apicentral.rtdbrasil.org.br/documento'}
            cliente.atualizacoes.return_value = {'Data':[dados(p1),dados(p2)],'Number':1,'TotalPages':1}
            cliente.pedido.side_effect = dados
            cliente.baixar.return_value = b'%PDF-teste'
            with patch.object(sync, 'TRAVA', 123998877), patch.object(sync, 'conectar', conectar_teste), patch.object(sync, 'extrair_documento_pdf', return_value={'ins':['IN01669965C'],'destinatarios':[]}), patch('backend.app.rotas.rtd_intimacoes.conectar', conectar_teste), patch('backend.app.rotas.rtd_intimacoes.registrar_auditoria_cursor'):
                r = sync.executar_passo_rtd(cliente)
                self.assertEqual(r['vinculados'],2)
                with con.cursor() as c:
                    itens = sync.anexar_rtd(c,[{'id':str(alvo)}],'teste1')
                    self.assertEqual(len(itens[0]['rtd']),2)
                    self.assertTrue(all(x['novo'] for x in itens[0]['rtd']))
                    c.execute('SELECT COUNT(*) AS n FROM rtd_eventos_aeri')
                    self.assertEqual(c.fetchone()['n'],2)
                    # Reprocessamento idempotente.
                    c.execute('UPDATE rtd_pedidos_aeri SET pendente=TRUE')
                con.commit()
                sync.executar_passo_rtd(cliente)
                with con.cursor() as c:
                    c.execute('SELECT COUNT(*) AS n FROM rtd_eventos_aeri')
                    self.assertEqual(c.fetchone()['n'],2)
                    c.execute('UPDATE rtd_pedidos_aeri SET pendente=TRUE WHERE protocolo=%s',(p1,))
                con.commit()
                cliente.pedido.side_effect = lambda p: {**dados(p),'Situacao':'Aguardando Pagamento'}
                sync.executar_passo_rtd(cliente)
                marcar_lido(p1,Leitura(versao=1),None,'teste1')
                with con.cursor() as c:
                    pedidos = sync.anexar_rtd(c,[{'id':str(alvo)}],'teste1')[0]['rtd']
                    self.assertTrue(next(p for p in pedidos if p['protocolo']==p1)['novo'])
                marcar_lido(p1,Leitura(versao=2),None,'teste1')
                with con.cursor() as c:
                    pedidos = sync.anexar_rtd(c,[{'id':str(alvo)}],'teste1')[0]['rtd']
                    self.assertFalse(next(p for p in pedidos if p['protocolo']==p1)['novo'])
                    pedidos = sync.anexar_rtd(c,[{'id':str(alvo)}],'teste2')[0]['rtd']
                    self.assertTrue(next(p for p in pedidos if p['protocolo']==p1)['novo'])
                    # Falha de rede mantém checkpoint, registra falha e remarca tentativa.
                    c.execute('UPDATE rtd_sincronizacao_aeri SET proxima_consulta=NOW()')
                con.commit()
                cliente.atualizacoes.side_effect = sync.ErroRTD('RTD_REDE: teste')
                self.assertEqual(sync.executar_passo_rtd(cliente)['estado'],'ERRO')
                with con.cursor() as c:
                    c.execute('SELECT erro,pagina FROM rtd_sincronizacao_aeri')
                    self.assertEqual(c.fetchone(), {'erro':'RTD_REDE: teste','pagina':1})
                # Completa lacuna importada e preserva uma edição humana posterior.
                with con.cursor() as c, patch.object(sync,'registrar_auditoria_cursor'):
                    c.execute("UPDATE intimacoes_aeri SET devedor='Aguardando identificação no documento RTD'")
                    c.execute('SELECT * FROM rtd_pedidos_aeri WHERE protocolo=%s',(p1,))
                    anterior=c.fetchone(); anterior['documento_hash']=None
                    with patch.object(sync,'extrair_documento_pdf',return_value={'ins':['IN01669965C'],'destinatarios':['PESSOA TESTE']}):
                        sync.salvar_pedido(c,anterior,dados(p1),cliente)
                    c.execute('SELECT devedor FROM intimacoes_aeri')
                    self.assertEqual(c.fetchone()['devedor'],'PESSOA TESTE')
                    c.execute("UPDATE intimacoes_aeri SET devedor='EDITADO PELA EQUIPE'")
                    c.execute('SELECT * FROM rtd_pedidos_aeri WHERE protocolo=%s',(p1,))
                    anterior=c.fetchone(); anterior['documento_hash']=None
                    with patch.object(sync,'extrair_documento_pdf',return_value={'ins':['IN01669965C'],'destinatarios':['OUTRA PESSOA']}):
                        sync.salvar_pedido(c,anterior,dados(p1),cliente)
                    c.execute('SELECT devedor FROM intimacoes_aeri')
                    self.assertEqual(c.fetchone()['devedor'],'EDITADO PELA EQUIPE')


if __name__ == '__main__': unittest.main()
