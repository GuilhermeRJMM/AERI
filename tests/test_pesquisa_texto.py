"""Regressões da geração de texto: nomes equivalentes e índice antigo."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.rotas import buscas
from backend.app.servicos import pesquisa_titularidade as pesquisa


def titular(**alteracoes):
    return dict(dict(numero=37404, nome='Eduardo Costa da Nóbrega',
                     nome_busca='EDUARDO COSTA DA NOBREGA', documento_hash='hash-teste',
                     documento_mascarado='***.***.578-50', tipo_documento='CPF',
                     proporcao='100%', origem='R.04', situacao='ATIVA', confianca='ALTA',
                     veredito_cadeia='OK', indice_busca_versao=2,
                     consultado_em=datetime.now(timezone.utc)), **alteracoes)


def cursor_pesquisa(linhas=(), candidatos=(), cobertura=None):
    cur = MagicMock()
    cur.fetchone.side_effect = [dict(total=len(linhas), matriculas=len(linhas)),
                               cobertura or dict(sem_titular=0, mencoes_pendentes=39467, mais_antiga=None)]
    cur.fetchall.side_effect = [list(linhas), list(candidatos)]
    return cur


class TestePesquisaTexto(unittest.TestCase):
    def test_nome_do_video_preserva_todos_os_sobrenomes(self):
        nome = 'Eduardo da Costa Nóbrega'
        self.assertEqual(pesquisa.palavras_nome(nome), pesquisa.palavras_nome('Eduardo Costa da Nobrega'))
        self.assertNotEqual(pesquisa.palavras_nome(nome), pesquisa.palavras_nome('Eduardo Nobrega'))
        self.assertNotEqual(pesquisa.palavras_nome(nome), pesquisa.palavras_nome('Eduardo Costa Nobrega Junior'))
        self.assertNotEqual(pesquisa.palavras_nome('Maria Maria Silva'), pesquisa.palavras_nome('Maria Silva'))
        sql, params, _, _ = pesquisa.filtros_identidade(nome, '', exata=True)
        self.assertIn('regexp_split_to_table', sql)
        self.assertNotIn('LIKE', sql)
        self.assertEqual([['COSTA', 'EDUARDO', 'NOBREGA']], params)

    def test_exportacao_positiva_nao_bloqueia_por_lacunas_de_outras_pessoas(self):
        cur = cursor_pesquisa([titular()])
        resultado = pesquisa.pesquisar(cur, 'Eduardo da Costa Nobrega', exportar=True)
        self.assertEqual(37404, resultado['itens'][0]['matricula'])
        self.assertEqual('NOME_EQUIVALENTE', resultado['itens'][0]['correspondencia'])
        self.assertFalse(resultado['itens'][0]['revisaoPendente'])

    def test_indice_antigo_continua_bloqueado_sem_reconsulta(self):
        cur = cursor_pesquisa([titular(indice_busca_versao=1)])
        with self.assertRaises(HTTPException) as erro:
            pesquisa.pesquisar(cur, 'Eduardo da Costa Nobrega', exportar=True)
        self.assertEqual(409, erro.exception.status_code)

    def test_previa_interna_identifica_pendencia_sem_liberar_texto(self):
        cur = cursor_pesquisa([titular(indice_busca_versao=1)])
        resultado = pesquisa.pesquisar(cur, 'Eduardo da Costa Nobrega', exportar=True, validar_exportacao=False)
        self.assertTrue(resultado['itens'][0]['revisaoPendente'])

    def test_homonimos_exigem_documento_mesmo_apos_conferencia(self):
        cur = cursor_pesquisa([titular(), titular(numero=10, documento_hash='outro-hash')])
        with self.assertRaises(HTTPException) as erro:
            pesquisa.pesquisar(cur, 'Eduardo da Costa Nobrega', exportar=True)
        self.assertIn('documentos diferentes', erro.exception.detail)

    def test_negativa_com_lacunas_continua_bloqueada(self):
        cur = cursor_pesquisa()
        contagem = dict(total=0, matriculas=0)
        cobertura = dict(sem_titular=0, mencoes_pendentes=39467, mais_antiga=None)
        cur.fetchone.side_effect = [contagem, cobertura, contagem, cobertura]
        cur.fetchall.side_effect = [[], [], [], []]
        # A consulta aproximada também não encontra titulares.
        with self.assertRaises(HTTPException) as erro:
            pesquisa.pesquisar(cur, 'Pessoa inexistente', exportar=True)
        self.assertIn('lacunas', erro.exception.detail)

    def test_nome_parcial_nao_vira_negativa(self):
        cur = cursor_pesquisa(cobertura=dict(sem_titular=0, mencoes_pendentes=0, mais_antiga=None))
        original = pesquisa.pesquisar
        def executar(*args, **kwargs):
            if not kwargs.get('exportar'):
                return {'total': 1}
            return original(*args, **kwargs)
        with patch.object(pesquisa, 'pesquisar', side_effect=executar):
            with self.assertRaises(HTTPException) as erro:
                executar(cur, 'Eduardo', exportar=True)
        self.assertIn('nomes parciais', erro.exception.detail)

    def test_cpf_diferente_nunca_e_incluido(self):
        with patch.dict(os.environ, {'AERI_BUSCAS_HMAC_KEY': 'chave-somente-testes'}):
            protegido = pesquisa.hash_documento('12345678901')
            cur = cursor_pesquisa([titular(documento_hash='diferente')])
            cur.fetchone.side_effect = [dict(total=0), dict(total=1, matriculas=1),
                                       dict(sem_titular=1, mencoes_pendentes=0, mais_antiga=None)]
            with self.assertRaises(HTTPException) as erro:
                pesquisa.pesquisar(cur, documento='12345678901', exportar=True)
            self.assertIn('lacunas', erro.exception.detail)
            self.assertNotEqual('diferente', protegido)


class TestePreparacaoTexto(unittest.TestCase):
    def previa(self, pendente=True):
        return dict(itens=[dict(matricula=37404, revisaoPendente=pendente)], candidatos=[], maisCandidatos=False)

    def test_reconsulta_somente_matricula_encontrada_e_exige_validacao_final(self):
        con = MagicMock()
        con.__enter__.return_value = con
        cur = con.cursor.return_value.__enter__.return_value
        final = dict(itens=[dict(matricula=37404, revisaoPendente=False)])
        with patch.object(buscas, 'conectar', return_value=con), \
             patch.object(pesquisa, 'pesquisar', side_effect=[self.previa(), final]) as pesquisar, \
             patch.object(buscas, 'validar_configuracao_buscas'), \
             patch.object(buscas, '_consultar_lote', return_value=([dict(numero=37404, status='OK', texto='texto-teste')], None)) as consultar, \
             patch.object(buscas, '_salvar_indice') as salvar, \
             patch.object(buscas, 'registrar_auditoria_cursor') as auditar:
            resultado = buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='Eduardo da Costa Nobrega'), None, 'usuario')
        consultar.assert_called_once_with([37404])
        salvar.assert_called_once_with(cur, 37404, 'texto-teste', permitir_complemento=False)
        self.assertEqual(1, resultado['reconsultadas'])
        self.assertNotIn('validar_exportacao', pesquisar.call_args.kwargs)
        self.assertNotIn('Eduardo', str(auditar.call_args))
        con.commit.assert_called_once()

    def test_sem_pendencias_nao_consulta_tri7(self):
        with patch.object(buscas, 'conectar'), \
             patch.object(pesquisa, 'pesquisar', side_effect=[self.previa(False), {'itens': []}]), \
             patch.object(buscas, '_consultar_lote') as consultar:
            resultado = buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='Eduardo'), None, 'usuario')
        consultar.assert_not_called()
        self.assertEqual(0, resultado['reconsultadas'])

    def test_resposta_vazia_tri7_nao_apaga_indice_nem_gera_negativa(self):
        with patch.object(buscas, 'conectar'), \
             patch.object(pesquisa, 'pesquisar', return_value=self.previa()), \
             patch.object(buscas, 'validar_configuracao_buscas'), \
             patch.object(buscas, '_consultar_lote', return_value=([dict(numero=37404, status='SEM_TEXTO')], None)), \
             patch.object(buscas, '_salvar_indice') as salvar:
            with self.assertRaises(HTTPException) as erro:
                buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='Eduardo'), None, 'usuario')
        self.assertEqual(502, erro.exception.status_code)
        salvar.assert_not_called()

    def test_limite_evitar_reindexacao_global(self):
        previa = self.previa()
        previa['itens'] = [dict(matricula=i, revisaoPendente=True) for i in range(21)]
        with patch.object(buscas, 'conectar'), patch.object(pesquisa, 'pesquisar', return_value=previa), \
             patch.object(buscas, '_consultar_lote') as consultar:
            with self.assertRaises(HTTPException) as erro:
                buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='Eduardo'), None, 'usuario')
        self.assertEqual(409, erro.exception.status_code)
        consultar.assert_not_called()

    def test_cpf_no_campo_nome_e_validado(self):
        with patch.object(buscas, 'conectar'), \
             patch.object(pesquisa, 'pesquisar', side_effect=[self.previa(False), {}]) as pesquisar:
            buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='123.456.789-01'), None, 'usuario')
        self.assertEqual(('', '123.456.789-01'), pesquisar.call_args.args[1:])
        with self.assertRaises(HTTPException):
            buscas.preparar_texto_pesquisa(buscas.PesquisaTexto(nome='12345678901', documento='98765432100'), None, 'usuario')

    def test_rota_protegida_por_sessao_csrf_e_limites_de_entrada(self):
        rota = next(r for r in buscas.router.routes if r.path.endswith('/preparar-texto'))
        self.assertIn(buscas.proteger_csrf, [d.dependency for d in rota.dependencies])
        self.assertTrue(any(d.name == 'usuario' for d in rota.dependant.dependencies))
        with self.assertRaises(ValidationError):
            buscas.PesquisaTexto(nome='a' * 301)


if __name__ == '__main__':
    unittest.main()
