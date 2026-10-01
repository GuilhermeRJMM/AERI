import io
import unittest
from datetime import date
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from pypdf import PdfWriter
from backend.app.servicos.rtd_cliente import (
    ClienteRTD, ErroRTD, validar_url, identificar_ins, identificar_destinatarios, extrair_ins_pdf, retrato, hash_resumo,
)
from backend.app.servicos.rtd_sincronizacao import decidir_vinculo, salvar_pedido, executar_passo_rtd

PROTOCOLO = '20260924145692380'


class TesteRTD(unittest.TestCase):
    def test_rotas_exigem_login_e_csrf(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.app.rotas.rtd_intimacoes import router
        from backend.app.database import preparar_banco
        app=FastAPI(); app.include_router(router)
        app.dependency_overrides[preparar_banco]=lambda: None
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/rtd-intimacoes/status').status_code,401)
            self.assertEqual(client.post('/api/rtd-intimacoes/'+PROTOCOLO+'/lido',json={'versao':1}).status_code,403)

    def test_destinatarios_variacoes_e_nao_credor(self):
        for titulo in ('Ao Ilmo Sr.', 'Ao Ilmo(a) Sr(a).', 'À Ilma. Sra.'):
            self.assertEqual(identificar_destinatarios(titulo+' MARIA DE TESTE(CPF: 000.000.000-00).'),['MARIA DE TESTE'])
        self.assertEqual(identificar_destinatarios('Credor: BANCO DE TESTE (CPF: 000)'),[])

    def test_somente_desistencia_concluida_sai_da_tratativa(self):
        from scripts.importar_intimacoes_relatorio import em_tratativa
        self.assertTrue(em_tratativa('Desistência'))
        for status in ('Desistência Concluída','Arquivamento por desinteresse','Registro / Averbação','Entrega das importâncias recebidas'):
            self.assertFalse(em_tratativa(status))

    def test_certidao_c_nao_bloqueia_diligencias(self):
        c = ClienteRTD('teste')
        c.json=Mock(return_value={'Number':1,'TotalPages':1,'Data':[
            {'Protocolo':PROTOCOLO,'Situacao':'Orçamento'},
            {'Protocolo':PROTOCOLO+'C','Situacao':'Concluído'}]})
        d=c.atualizacoes(date(2026,1,1),1)
        self.assertEqual(len(d['Data']),1)
        self.assertEqual(d['OutrosServicos'],1)

    def test_in_repetido_e_espacado(self):
        self.assertEqual(identificar_ins('IN01669965C\nIN 01669965 C'), ['IN01669965C'])

    def test_nao_confunde_numero_ou_in_parcial(self):
        self.assertEqual(identificar_ins('IN123C XIN01669965C IN01669965CX 01669965'), [])

    def test_mais_de_um_in_nao_escolhe_primeiro(self):
        self.assertEqual(decidir_vinculo(['IN00000001C', 'IN00000002C'], ['a'], ['a']), (None, 'IN_AMBIGUO'))

    def test_vincula_somente_correspondencia_exata(self):
        self.assertEqual(decidir_vinculo(['IN01669965C'], ['a'], []), ('a', 'DOCUMENTO'))
        self.assertEqual(decidir_vinculo(['IN01669965C'], [], []), (None, 'IN_NAO_CADASTRADO'))

    def test_nao_sobrepoe_vinculo_divergente(self):
        self.assertEqual(decidir_vinculo(['IN01669965C'], ['b'], [], 'a'), ('a', 'CONFLITO'))
        self.assertEqual(decidir_vinculo(['IN01669965C'], ['b'], ['a']), (None, 'CONFLITO'))

    def test_preserva_legado_sem_documento(self):
        self.assertEqual(decidir_vinculo([], [], ['a']), ('a', 'CADASTRO_EXISTENTE'))
        self.assertEqual(decidir_vinculo([], [], []), (None, 'SEM_IN'))

    def test_multiplos_rtd_podem_ter_mesmo_in(self):
        for _ in range(2):
            self.assertEqual(decidir_vinculo(['IN01669965C'], ['a'], []), ('a', 'DOCUMENTO'))

    def test_url_restrita(self):
        for url in ('http://apicentral.rtdbrasil.org.br/a', 'https://evil.com/a',
                    'https://apicentral.rtdbrasil.org.br.evil.com/a',
                    'https://user@apicentral.rtdbrasil.org.br/a',
                    'https://apicentral.rtdbrasil.org.br:8000/a'):
            with self.subTest(url=url), self.assertRaises(ErroRTD):
                validar_url(url)

    def test_pdf_invalido_e_sem_texto(self):
        with self.assertRaises(ErroRTD):
            extrair_ins_pdf(b'<html>erro</html>')
        buffer = io.BytesIO()
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.write(buffer)
        self.assertEqual(extrair_ins_pdf(buffer.getvalue()), [])

    def test_retrato_nao_guarda_urls_documentos_ou_partes(self):
        d = retrato({'Situacao':'Orçamento', 'UrlArquivoEnviado':'https://privado', 'Devedor':'Pessoa'})
        self.assertNotIn('UrlArquivoEnviado', d)
        self.assertNotIn('Devedor', d)
        self.assertTrue(d['TemArquivoEnviado'])

    def test_hash_ignora_url_assinada_e_detecta_situacao(self):
        a = {'Situacao':'Orçamento','UrlArquivoEnviado':'a'}
        self.assertEqual(hash_resumo(a), hash_resumo({**a, 'UrlArquivoEnviado':'b'}))
        self.assertNotEqual(hash_resumo(a), hash_resumo({**a,'Situacao':'Aguardando Pagamento'}))

    def test_paginacao_valida_e_data_sem_hora(self):
        c = ClienteRTD('teste'); c.json = Mock(return_value={'Data':[],'Number':1,'TotalPages':0})
        c.atualizacoes(date(2026,9,28),1)
        c.json.assert_called_once_with('/api/pedido/2026-09-28?page=1&size=20')
        c.json.return_value = {'Data':[], 'Number':1,'TotalPages':2}
        with self.assertRaises(ErroRTD): c.atualizacoes(date(2026,9,28),1)

    def test_pedido_valida_identidade(self):
        c = ClienteRTD('teste'); c.json = Mock(return_value={'Situacao':'Teste','Protocolo':'outro'})
        with self.assertRaises(ErroRTD): c.pedido(PROTOCOLO)

    def test_erro_http_nao_revela_chave_ou_url(self):
        c = ClienteRTD('SEGREDO')
        c.opener.open = Mock(side_effect=HTTPError('https://privado',401,'SEGREDO',{},None))
        with self.assertRaises(ErroRTD) as erro: c.pedido(PROTOCOLO)
        self.assertNotIn('SEGREDO', str(erro.exception)); self.assertNotIn('privado', str(erro.exception))

    def test_sem_config_nao_toca_banco(self):
        with patch.dict('os.environ',{},clear=True), patch('backend.app.servicos.rtd_sincronizacao.conectar') as db:
            self.assertEqual(executar_passo_rtd()['estado'],'SEM_CONFIGURACAO')
            db.assert_not_called()

    def test_estado_repetido_nao_gera_evento(self):
        cur = Mock(); cur.fetchall.side_effect = [[{'id':'a'}], []]
        dados = {'Situacao':'Aguardando Pagamento'}
        anterior = dict(protocolo=PROTOCOLO, candidatos=['IN01669965C'], documento_hash='x',
                        dados=retrato(dados), versao=1, intimacao_id='a', erro=None, vinculo='DOCUMENTO')
        # Sem URL a origem passa para legado; confirme idempotência com legado real.
        anterior.update(candidatos=[], vinculo='CADASTRO_EXISTENTE')
        cur.fetchall.side_effect = [[], [{'id':'a'}]]
        self.assertEqual(salvar_pedido(cur, anterior, dados, Mock()), (True, False))
        self.assertFalse(any('INSERT INTO rtd_eventos' in x.args[0] for x in cur.execute.call_args_list))

    def test_mudanca_gera_evento_sem_alterar_intimacao(self):
        cur = Mock(); cur.fetchall.side_effect = [[], [{'id':'a'}]]
        anterior = dict(protocolo=PROTOCOLO, candidatos=[], dados=retrato({'Situacao':'Orçamento'}),
                        versao=1, intimacao_id='a', erro=None, vinculo='CADASTRO_EXISTENTE')
        self.assertEqual(salvar_pedido(cur, anterior, {'Situacao':'Aguardando Pagamento'}, Mock()), (True, True))
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        self.assertTrue(any('INSERT INTO rtd_eventos' in s for s in sqls))
        self.assertFalse(any('UPDATE intimacoes_aeri' in s for s in sqls))


if __name__ == '__main__': unittest.main()
