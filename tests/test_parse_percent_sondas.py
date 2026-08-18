"""Cobertura das sondas de parse_percent que o acervo quase não exercita.

O corpus de regressão aciona quatro das sete sondas; as três de quinhão
(percentual sobre percentual, partes avaliadas em dinheiro e declaração
direta) só aparecem em inventário e ficavam sem teste. Os valores abaixo
são os que o motor já produzia antes de a função ser dividida.
"""
import unittest

from backend.app.proprietarios import parse_percent


class TestePercentualSobreQuinhao(unittest.TestCase):
    def test_percentual_da_quota_multiplica_os_dois(self):
        # 50% de uma quota de 30% são 15% do imóvel, não 50%.
        self.assertAlmostEqual(
            parse_percent("coube-lhe 50% da quota ( 30% ) do acervo"), 15.0)

    def test_percentual_incidente_sobre_quinhao_nao_vale_pelo_todo(self):
        self.assertAlmostEqual(
            parse_percent(
                "em pagamento de seu quinhao, 4,1666% incidentes sobre 50% do imovel"),
            2.0833)

    def test_parte_em_dinheiro_sobre_quinhao(self):
        self.assertAlmostEqual(
            parse_percent(
                "parte ideal no valor de 10.000,00 incidente sobre 50% do imovel "
                "avaliado por R$ 100.000,00"),
            5.0)


class TestePercentualDeclarado(unittest.TestCase):
    def test_corresponde_a_percentual_do_imovel(self):
        self.assertAlmostEqual(
            parse_percent("o que corresponde a 25% do imovel"), 25.0)

    def test_percentual_das_partes_a_saber(self):
        self.assertAlmostEqual(
            parse_percent("30% das partes a saber: os herdeiros"), 30.0)

    def test_varias_partes_do_mesmo_percentual_somam(self):
        self.assertAlmostEqual(
            parse_percent("duas partes ideais correspondentes a 10% cada"), 20.0)


class TestePercentualPorPartesAvaliadas(unittest.TestCase):
    def test_duas_partes_em_dinheiro_somam_antes_de_dividir(self):
        self.assertAlmostEqual(
            parse_percent(
                "duas partes ideais de 100,00 e 200,00, na avaliacao de 1.000,00"),
            30.0)

    def test_percentual_sobre_parte_ideal_em_dinheiro(self):
        self.assertAlmostEqual(
            parse_percent(
                "50% da parte ideal de R$ 100,00, na avaliacao de R$ 400,00"),
            12.5)

    def test_fracao_sobre_parte_ideal_em_dinheiro(self):
        self.assertAlmostEqual(
            parse_percent(
                "1/2 da parte ideal de 500,00, na avaliacao de 1.000,00"), 25.0)


class TesteOrdemDasSondas(unittest.TestCase):
    def test_percentual_declarado_prevalece_sobre_valor_monetario(self):
        # Sem a prioridade, "parte ideal de 50% ... avaliação de 700.000,10"
        # era lido como 50 dividido por 700.000,10.
        self.assertAlmostEqual(
            parse_percent(
                "parte ideal de 50%, na avaliacao de 700.000,10"), 50.0)

    def test_ato_sem_proporcao_declarada_transmite_o_todo(self):
        self.assertAlmostEqual(parse_percent("venda e compra do imovel"), 100.0)


if __name__ == "__main__":
    unittest.main()
