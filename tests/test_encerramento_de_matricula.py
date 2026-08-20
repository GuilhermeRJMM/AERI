"""Detecção de encerramento, aferida contra o relatório da serventia.

O relatório de 17/08/2026 lista 10.744 matrículas encerradas. O motor
reconhecia 8.262: as outras 2.482 saíam como ATIVA, e uma busca por
titularidade as devolvia como se o imóvel estivesse vigente.

Todas as redações abaixo foram colhidas de matrículas reais do acervo de
Morrinhos, conferidas uma a uma contra esse relatório.
"""
import unittest

from backend.app.servicos.dados_imovel import (
    _tem_desmembramento_integral,
    _tem_encerramento_explicito,
    _tem_saida_integral_do_imovel,
)


class TesteDesmembramentoIntegral(unittest.TestCase):
    """Todo o imóvel vira outras matrículas; não sobra remanescente."""

    def test_rural_em_duas_glebas(self):
        # Matrícula 1, AV.08 de 1996.
        self.assertTrue(_tem_desmembramento_integral(
            "AVERBA-SE O DESMEMBRAMENTO DO IMOVEL MATRICULADO EM DUAS GLEBAS DE TERRAS"))

    def test_termo_digitado_errado_no_acervo(self):
        # Matrícula 8, AV-04 de 1992: "desmebramento", sem o segundo M.
        self.assertTrue(_tem_desmembramento_integral(
            "AVERBA-SE O DESMEBRAMENTO DO IMOVEL MATRICULADO EM DUAS GLEBAS DE TERRAS"))
        self.assertTrue(_tem_desmembramento_integral(
            "AVERBA-SE O DESMENBRAMENTO DO IMOVEL MATRICULADO EM DUAS GLEBAS"))

    def test_urbano_diz_lote_e_usa_o_masculino(self):
        # Matrícula 2.946, AV.12 de 2002. A lista de quantidades só tinha
        # o feminino DUAS, então todo desmembramento urbano escapava.
        self.assertTrue(_tem_desmembramento_integral(
            "AVERBA-SE O DESMEMBRAMENTO DO LOTE CONSTANTE DA PRESENTE MATRICULA, "
            "EM DOIS (02) IMOVEIS INDEPENDENTES, A SABER"))

    def test_urbano_em_dois_lotes(self):
        # Matrícula 7.619, AV-5 de 2011.
        self.assertTrue(_tem_desmembramento_integral(
            "AVERBA-SE O DESMEMBRAMENTO DO IMOVEL OBJETO DA PRESENTE MATRICULA, "
            "EM DOIS LOTES DE TERRAS SENDO"))

    def test_desmembramento_parcial_nao_encerra(self):
        # Matrículas 1.863, 2.362, 2.651, 3.569, 3.859: sai uma parte e o
        # remanescente continua vivo. Tratar isso como encerramento
        # mataria a maioria das rurais antigas, que já sofreram
        # desmembramento parcial em algum momento.
        for redacao in (
            "EM VIRTUDE DE DIVISAO, DESMEMBROU-SE DO IMOVEL OBJETO DA PRESENTE "
            "MATRICULA UM TERRENO COM A AREA DE 769,00M2",
            "EM VIRTUDE DE DIVISAO DESMEMBROU-SE DESTA MATRICULA, UM IMOVEL COM "
            "A AREA DE 83,85,02 HECTARES",
        ):
            with self.subTest(redacao=redacao[:45]):
                self.assertFalse(_tem_desmembramento_integral(redacao))

    def test_remanescente_na_frase_impede_o_encerramento(self):
        self.assertFalse(_tem_desmembramento_integral(
            "AVERBA-SE O DESMEMBRAMENTO DO IMOVEL EM DUAS GLEBAS, "
            "FICANDO O REMANESCENTE NESTA MATRICULA"))


class TesteSaidaIntegralDoImovel(unittest.TestCase):
    """O imóvel inteiro passa a viver em outra matrícula."""

    def test_remanescente_vira_outra_matricula(self):
        # Matrícula 2, AV.08 de 1984: o que sobrou dos desmembramentos
        # anteriores saiu, e aqui não fica nada.
        self.assertTrue(_tem_saida_integral_do_imovel(
            "O REMANESCENTE DO IMOVEL CONSTANTE DA AV.07-SUPRA COM 76,99,55 HA; "
            "FOI MATRICULADO SOB O N 5.262, FLS. 261, DO L 2-T"))

    def test_usucapiao_rematricula_o_imovel_inteiro(self):
        # Matrícula 1.404, AV.07 de 1979.
        self.assertTrue(_tem_saida_integral_do_imovel(
            "O IMOVEL OBJETO DA PRESENTE MATRICULA E R.06, FOI USUCAPIDO PELOS "
            "SEUS PROPRIETARIOS E EM CONSEQUENCIA MATRICULADO E REGISTRADO "
            "NOVAMENTE SOB O N 2.646, FLS. 101"))

    def test_unificacao_com_outras_matriculas(self):
        # Matrícula 2.245, de 1988.
        self.assertTrue(_tem_saida_integral_do_imovel(
            "O IMOVEL OBJETO DO PRESENTE REGISTRO FOI UNIFICADO AO REMANESCENTE "
            "DA MATRICULA 5.523 E AOS IMOVEIS REGISTRADOS SOB OS N.OS R.3-2.241 "
            "E, EM CONSEQUENCIA MATRICULADO SOB O N 7.716, FLS 71"))

    def test_texto_sem_saida_do_imovel_nao_encerra(self):
        self.assertFalse(_tem_saida_integral_do_imovel(
            "CANCELAMENTO DE HIPOTECA POR QUITACAO DADA PELO CREDOR"))
        self.assertFalse(_tem_saida_integral_do_imovel(
            "LIBERACAO E SUBSTITUICAO DA AREA HIPOTECADA"))


class TesteEncerramentoExplicito(unittest.TestCase):
    def test_redacoes_que_ja_eram_reconhecidas(self):
        for redacao in (
            "FICA ENCERRADA A PRESENTE MATRICULA",
            "ENCERRA-SE A PRESENTE MATRICULA",
            "COM O QUE FICA ENCERRADA",
            "CANCELA-SE A PRESENTE MATRICULA",
        ):
            with self.subTest(redacao=redacao):
                self.assertTrue(_tem_encerramento_explicito(redacao))

    def test_cancelamento_de_hipoteca_nao_e_encerramento(self):
        # A palavra "cancelamento" sozinha não encerra matrícula: quase
        # todo acervo antigo tem cancelamento de hipoteca.
        self.assertFalse(_tem_encerramento_explicito(
            "AV.04-01 CANCELAMENTO DE HIPOTECA POR QUITACAO DADA PELO CREDOR, "
            "PARA CONSTAR QUE OS REGISTROS FIQUEM CANCELADOS"))


if __name__ == "__main__":
    unittest.main()
