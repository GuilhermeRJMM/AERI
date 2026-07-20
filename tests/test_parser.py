import unittest

from backend.app.parser import separar_atos


class TesteParserAtos(unittest.TestCase):
    def test_aceita_formatos_historicos_retornados_pela_tri7(self):
        texto = """MATRÍCULA 1
R.01 - COMPRA E VENDA.
AV-02- RETIFICAÇÃO.
— AV. 03 – CANCELAMENTO.
R.04 descrição sem segundo separador.
"""
        atos = separar_atos(texto)
        self.assertEqual([ato["codigo"] for ato in atos], ["R.01", "AV.02", "AV.03", "R.04"])
        self.assertIn("COMPRA E VENDA", atos[0]["texto"])
        self.assertIn("descrição sem segundo separador", atos[-1]["texto"])

    def test_nao_trata_lista_de_referencias_com_virgula_como_novo_ato(self):
        texto = """MATRÍCULA 1
R.01 - COMPRA E VENDA.
R.07, R.09 e AV.10 são referências internas.
AV.02 - RETIFICAÇÃO.
"""
        atos = separar_atos(texto)
        self.assertEqual([ato["codigo"] for ato in atos], ["R.01", "AV.02"])
        self.assertIn("R.07, R.09", atos[0]["texto"])

    def test_aceita_virgula_quando_codigo_segue_sequencia_registral(self):
        texto = """MATRÍCULA 1
R.01, COMPRA E VENDA.
AV.02, RETIFICAÇÃO.
"""
        self.assertEqual([ato["codigo"] for ato in separar_atos(texto)], ["R.01", "AV.02"])

    def test_ignora_codigo_repetido_usado_como_referencia(self):
        texto = """MATRÍCULA 1
R.01 - COMPRA E VENDA.
AV.02 - RETIFICAÇÃO.
R.01 descrição da referência interna.
AV.03 - ENCERRAMENTO.
"""
        self.assertEqual([ato["codigo"] for ato in separar_atos(texto)], ["R.01", "AV.02", "AV.03"])

    def test_normaliza_numero_de_ato_com_erro_de_ocr(self):
        texto = """MATRÍCULA 1
AV-L CANCELAMENTO.
R.O2 - COMPRA E VENDA.
"""
        self.assertEqual([ato["codigo"] for ato in separar_atos(texto)], ["AV.1", "R.02"])


if __name__ == "__main__":
    unittest.main()
