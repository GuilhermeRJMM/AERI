"""Caixas B8 e B9: prazos, taxa contratada, minuta e complemento, sem acervo."""
import copy
import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from backend.app.contratos_nucleo import extrator, minuta
from backend.app.contratos_nucleo.ficha import Ficha, Juros
from backend.app.servicos.contratos import completar_juros_ausentes
from backend.app.servicos.documentos_contratos import extrair_documento


CABECALHO = ('B9 - Taxa de Juros: B9.1 B9.2 B9.3 B9.4 Sem Desconto: '
             'Com Desconto: Com Redutor de 0,5%: Taxa Contratada: ')
ROTULOS = ('Nominal % (a.a.)', 'Efetiva % (a.a.)', 'Efetiva % (a.m.)')
TAXAS = [('8.1600', 'Não se aplica', '7.6600', '7.6600'),
         ('8.4722', 'Não se aplica', '7.9347', '7.9347'),
         ('0.6800', 'Não se aplica', '0.6383', '0.6383')]
ESPERADO = Juros('7.6600', '7.9347', '0.6383')


def tabela(linhas=True, taxas=None, cabecalho=CABECALHO):
    taxas = taxas or TAXAS
    if linhas:
        corpo = ' '.join(' '.join([r] * 4) + ' ' + ' '.join(v) for r, v in zip(ROTULOS, taxas))
    else:
        corpo = ' '.join(' '.join(r + ' ' + v[i] for r, v in zip(ROTULOS, taxas)) for i in range(4))
    return cabecalho + corpo + ' B10 - Encargo Mensal Inicial: R$ 1.814,99'


def payload():
    original = asdict(Ficha())
    original['origens']['financiamento._alerta_juros'] = 'Tabela nao reconhecida anteriormente'
    return {'fichaOriginal': original, 'ficha': copy.deepcopy(original),
            'documento': {'texto': tabela(), 'paginas': [{'pagina': 2, 'texto': tabela()}]},
            'alertasExtracao': [{'campo': 'financiamento.juros.' + c, 'motivo': 'ausente'}
                                for c in asdict(Juros())]}


class JurosContratadosTests(unittest.TestCase):
    def test_tabela_ordenada_por_linhas(self):
        juros, origem = extrator._taxa_contratada(tabela())
        self.assertEqual(juros, ESPERADO)
        self.assertIn('linhas', origem)

    def test_tabela_por_colunas_continua_funcionando(self):
        self.assertEqual(extrator._taxa_contratada(tabela(False))[0], ESPERADO)

    def test_nao_escolhe_taxa_por_maior_menor_ou_coluna_redutor(self):
        taxas = [('8.1600', '4.0000', '6.0000', '5.0000'),
                 ('8.4722', '4.0742', '6.1678', '5.1162'),
                 ('0.6800', '0.3333', '0.5000', '0.4167')]
        for linhas in (True, False):
            self.assertEqual(extrator._taxa_contratada(tabela(linhas, taxas))[0],
                             Juros('5.0000', '5.1162', '0.4167'))

    def test_usa_rotulo_taxa_contratada_mesmo_em_outra_posicao(self):
        cab = CABECALHO.replace('Sem Desconto:', 'TMP:').replace('Taxa Contratada:', 'Sem Desconto:').replace('TMP:', 'Taxa Contratada:')
        for linhas in (True, False):
            self.assertEqual(extrator._taxa_contratada(tabela(linhas, cabecalho=cab))[0],
                             Juros('8.1600', '8.4722', '0.6800'))

    def test_linhas_incompletas_nao_escolhem_simulacao(self):
        for perdido in ('7.6600', '7.9347', '0.6383', 'Não se aplica'):
            with self.subTest(perdido=perdido):
                self.assertIsNone(extrator._taxa_contratada(tabela().replace(perdido, '', 1))[0])

    def test_colunas_incompletas_nao_escolhem_primeiro_grupo(self):
        sem_contratada = tabela(False).rsplit('Nominal % (a.a.)', 1)[0] + 'B10 - Encargo Mensal Inicial'
        self.assertIsNone(extrator._taxa_contratada(sem_contratada)[0])

    def test_taxa_nao_aplicavel_nao_e_numero(self):
        taxas = [(*v[:3], 'Não se aplica') for v in TAXAS]
        for linhas in (True, False):
            self.assertIsNone(extrator._taxa_contratada(tabela(linhas, taxas))[0])

    def test_cabecalho_contratada_ausente_nao_autoriza_ultima_simulacao(self):
        self.assertIsNone(extrator._taxa_contratada(tabela().replace('Taxa Contratada:', 'Simulação:'))[0])

    def test_colunas_nomeadas_sem_taxa_contratada_usam_a_que_se_aplica(self):
        """Modelo MO30173Cv120: as colunas sao Balcao e Reduzida.

        Nenhuma se chama "Taxa Contratada", e o formulario escreve "Nao se
        aplica" na que nao foi contratada. Sem ler isso, o protocolo 185.863
        saia com a taxa em branco na minuta -- num contrato que traz 10,0000%
        escrito por extenso na caixa B9.1.
        """
        texto = ('B9 - Taxa de Juros: B9.1 - Balcão: B9.2 - Reduzida: '
                 'Nominal % (a.a.) 10.0000 Não se aplica '
                 'Efetiva %(a.a.) 10.4713 Não se aplica '
                 'Efetiva % (a.m.) 0.8333 Não se aplica '
                 'B10 - Encargo Mensal Inicial')
        juros, origem = extrator._taxa_contratada(texto)
        self.assertEqual(juros, Juros('10.0000', '10.4713', '0.8333'))
        self.assertIn('Balcão', origem)

    def test_duas_colunas_com_numero_e_sem_rotulo_contratada_nao_escolhem(self):
        """Duas colunas aplicáveis e nenhuma nomeada: não há o que escolher."""
        texto = ('B9 - Taxa de Juros: B9.1 - Balcão: B9.2 - Reduzida: '
                 'Nominal % (a.a.) 10.0000 9.0000 '
                 'Efetiva %(a.a.) 10.4713 9.3807 '
                 'Efetiva % (a.m.) 0.8333 0.7500 '
                 'B10 - Encargo Mensal Inicial')
        juros, motivo = extrator._taxa_contratada(texto)
        self.assertIsNone(juros)
        self.assertIn('mais de uma coluna', motivo)


    def test_ocr_com_coluna_contratada_depois_do_b13(self):
        parcial = tabela(False).rsplit('Nominal % (a.a.)', 1)[0]
        texto = parcial + 'B10 - Encargo Mensal Inicial B13 Forma de Pagamento '
        texto += '89.4 Taxa Contratada: Nominal % (a.a.) 4.5000 Efetiva % (a.a.) 4.5940 Efetiva % (a.m.) 0.3750'
        self.assertEqual(extrator._taxa_contratada(texto)[0], Juros('4.5000', '4.5940', '0.3750'))

    def test_pdf_digital_lido_por_linhas_ate_minuta(self):
        import pymupdf
        with pymupdf.open() as pdf:
            pagina = pdf.new_page()
            pagina.insert_text((30, 30), 'B9 - Taxa de Juros:')
            for i, titulo in enumerate(('Sem Desconto:', 'Com Desconto:', 'Com Redutor:', 'Taxa Contratada:')):
                x = 30 + i * 140
                pagina.insert_text((x, 50), f'B9.{i+1}', fontsize=9)
                pagina.insert_text((x, 65), titulo, fontsize=9)
                for n, rotulo in enumerate(ROTULOS):
                    pagina.insert_text((x, 85 + n * 40), rotulo, fontsize=9)
                    pagina.insert_text((x, 100 + n * 40), TAXAS[n][i], fontsize=9)
            pagina.insert_text((30, 220), 'B10 - Encargo Mensal Inicial')
            dados = pdf.tobytes()
        documento = extrair_documento(dados, permitir_ocr=False)
        ficha = extrator.extrai_do_texto(documento['texto'])
        self.assertEqual(ficha.financiamento.juros, ESPERADO)
        ato = minuta.alienacao_fiduciaria(ficha)
        self.assertIn('Nominal: 7,6600% a.a; Efetiva: 7,9347% a.a; Efetiva: 0,6383% a.m.', ato.texto)

    def test_minuta_com_taxas_vazias_gera_pendencias_visiveis(self):
        ato = minuta.alienacao_fiduciaria(Ficha())
        self.assertNotIn('Nominal: %', ato.texto)
        for rotulo in ('taxa nominal anual', 'taxa efetiva anual', 'taxa efetiva mensal'):
            self.assertIn(rotulo, ato.texto)
            self.assertTrue(any(p.campo == rotulo for p in ato.pendencias))

    def test_complementa_trabalho_antigo_sem_alterar_original(self):
        p = payload()
        original = copy.deepcopy(p['fichaOriginal'])
        self.assertTrue(completar_juros_ausentes(p))
        self.assertEqual(p['ficha']['financiamento']['juros'], asdict(ESPERADO))
        self.assertEqual(p['fichaOriginal'], original)
        self.assertEqual(p['alertasExtracao'], [])
        self.assertEqual(len(p['complementosExtracao']), 3)
        self.assertEqual(p['evidencias']['financiamento.juros.nominal_ao_ano']['paginas'], [2])
        self.assertFalse(completar_juros_ausentes(p))

    def test_taxa_editada_ou_apagada_manualmente_nao_e_sobrescrita(self):
        for lado in ('ficha', 'fichaOriginal'):
            p = payload()
            p[lado]['financiamento']['juros']['nominal_ao_ano'] = '4.1234'
            antes = copy.deepcopy(p)
            self.assertFalse(completar_juros_ausentes(p))
            self.assertEqual(p, antes)

    def test_sem_b9_nao_inventa_taxa_em_trabalho_antigo(self):
        p = payload()
        p['documento']['texto'] = 'Documento sem taxas'
        self.assertFalse(completar_juros_ausentes(p))
        self.assertEqual(p['ficha']['financiamento']['juros'], asdict(Juros()))

    def test_rota_de_reconfronto_complementa_juros_antes_de_comparar(self):
        from backend.app.rotas import contratos as rotas
        p = payload()
        original = copy.deepcopy(p['fichaOriginal'])
        id = uuid4()
        r = {'id': id, 'versao': 2, 'estado': 'MINUTA', 'payload_cifrado': 'teste'}
        req = SimpleNamespace(state=SimpleNamespace(sessao={'perfil': 'ADMIN'}))
        def confrontar(dados, *_):
            self.assertEqual(dados['ficha']['financiamento']['juros'], asdict(ESPERADO))
            return {'versaoRegras': rotas.VERSAO_CONFRONTO}
        with patch.object(rotas, 'conectar', MagicMock()), \
             patch.object(rotas, '_buscar', return_value=r), \
             patch.object(rotas, 'decifrar', return_value=p), \
             patch.object(rotas, 'cliente_tri7') as cli, \
             patch.object(rotas, 'confrontar', side_effect=confrontar), \
             patch('backend.app.rotas.analisador._regras_aprovadas', return_value=[]), \
             patch.object(rotas, '_salvar', return_value=r) as salvar, \
             patch.object(rotas, '_publico', return_value={}), \
             patch.object(rotas, 'registrar_auditoria_cursor'):
            cli.return_value.buscar_texto_matricula.return_value = {'texto': 'MATRÍCULA DE TESTE'}
            rotas.comparar(id, {'versao': 2, 'matricula': '10879', 'ficha': copy.deepcopy(p['ficha'])}, req, 'TESTE')
        self.assertEqual(p['fichaOriginal'], original)
        self.assertEqual(salvar.call_args.args[2]['ficha']['financiamento']['juros'], asdict(ESPERADO))


if __name__ == '__main__':
    unittest.main()


class PrazosDoB8Tests(unittest.TestCase):
    """A caixa B8 tem dois desenhos, e ler o errado troca o prazo do registro."""

    def prazos(self, texto):
        ficha = Ficha()
        extrator._financiamento(texto, ficha)
        return ficha.financiamento, ficha.origens

    def test_valor_colado_ao_rotulo_usa_a_amortizacao_e_nao_o_total(self):
        """O Total inclui a construcao; o que o ato registra e a amortizacao.

        "B8 - Prazo Total (meses): 429 B8.1 - Amortizacao (meses): 420 B8.2 -
        Construcao (meses): 9". Ler o Total poria 429 no lugar de 420 -- em 4
        dos 35 contratos medidos --, e nada acusaria.
        """
        texto = ('B8 - Prazo Total (meses): 429 B8.1 - Amortização (meses): 420 '
                 'B8.2 - Construção (meses): 9 B9 - Taxa de Juros: '
                 'B10 - Encargo Mensal Inicial')
        f, origens = self.prazos(texto)
        self.assertEqual(f.prazo_meses, '420')
        self.assertEqual(f.prazo_construcao, '09')
        self.assertEqual(origens['financiamento.prazo_meses'], 'caixa B8.1')

    def test_rotulo_sem_meses_entre_parenteses_tambem_e_lido(self):
        """Modelo MO30173Cv120 escreve "B8.1 - Amortização:", sem "(meses)"."""
        texto = ('B8 - Prazo Total (meses): 420 B8.1 - Amortização: 420 '
                 'B9 - Taxa de Juros: B10 - Encargo Mensal Inicial')
        f, _ = self.prazos(texto)
        self.assertEqual(f.prazo_meses, '420')

    def test_valores_em_bloco_depois_dos_rotulos_continuam_valendo(self):
        """O outro desenho: rotulos juntos, valores depois, na mesma ordem."""
        texto = ('B8 - Prazo Total (meses): B8.1 - Amortização (meses): '
                 'B8.2 - Construção (meses): 429 420 9 '
                 'B9 - Taxa de Juros: B10 - Encargo Mensal Inicial')
        f, origens = self.prazos(texto)
        self.assertEqual(f.prazo_meses, '420')
        self.assertEqual(f.prazo_construcao, '09')

    def test_modelo_sem_letra_ou_com_outra_letra_e_reconhecido(self):
        for rodape in ('MO30173Av120', 'MO30173Cv120', 'MO30809v016'):
            with self.subTest(rodape=rodape):
                ficha = extrator.extrai_do_texto(
                    f'{rodape} CONTRATO Nº 1.4444.2759316-9 {rodape}')
                self.assertEqual(ficha.contrato.modelo, rodape)
