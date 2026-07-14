import unittest

from backend.app.regras import identificar_tipo_onus
from backend.app.regras import extrair_grau_hipoteca
from backend.app.servicos.analise_matricula import analisar_matricula


class TesteTipoOnus(unittest.TestCase):
    def test_identifica_tipos_de_onus_ja_validados(self):
        casos = [
            ("R.01 - TRASLADO DE HIPOTECA oriunda de outra matrícula.", "HIPOTECA"),
            ("R.02 - HIPOTECA. O imóvel foi dado em hipoteca.", "HIPOTECA"),
            ("R.03 - ALIENAÇÃO FIDUCIÁRIA. Objeto da garantia: em alienação fiduciária.", "ALIENAÇÃO FIDUCIÁRIA"),
            ("R.04 - PENHORA do imóvel objeto da matrícula.", "PENHORA"),
            ("AV.05 - ASSUNÇÃO DE DÍVIDA garantida pelo imóvel.", "ASSUNÇÃO DE DÍVIDA"),
        ]

        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(identificar_tipo_onus(texto), esperado)

    def test_analise_informa_tipo_onus_no_ato(self):
        texto = """
        R.01-123 - TRASLADO DE HIPOTECA. Oriunda de outra matrícula, permanece
        a hipoteca cedular de primeiro grau sobre o imóvel.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(resultado["atos"][0]["categoria"], "ÔNUS")
        self.assertEqual(resultado["atos"][0]["tipo_onus"], "HIPOTECA")

    def test_extrai_grau_da_hipoteca(self):
        casos = [
            ("R.01 - HIPOTECA. Em hipoteca cedular de 1º grau.", 1),
            ("R.02 - HIPOTECA. Em segunda e especial hipoteca.", 2),
            ("R.03 - HIPOTECA. Em terceiro grau.", 3),
        ]

        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(extrair_grau_hipoteca(texto), esperado)

    def test_cancelamento_de_hipoteca_anterior_atualiza_grau_da_ativa(self):
        texto = """
        R.01-123 - HIPOTECA. Em hipoteca cedular de 1º grau, o imóvel objeto desta matrícula.
        R.02-123 - HIPOTECA. Em hipoteca cedular de 2º grau, o imóvel objeto desta matrícula.
        AV.03-123 - CANCELAMENTO. Fica cancelada a hipoteca constante do R.01 desta matrícula.
        """

        resultado = analisar_matricula(texto)
        atos = {ato["codigo"]: ato for ato in resultado["atos"]}

        self.assertEqual(atos["R.01"]["status"], "CANCELADO")
        self.assertIsNone(atos["R.01"]["grau_onus"])
        self.assertEqual(atos["R.02"]["status"], "ATIVO")
        self.assertEqual(atos["R.02"]["tipo_onus"], "HIPOTECA")
        self.assertEqual(atos["R.02"]["grau_onus"], "1º grau")


if __name__ == "__main__":
    unittest.main()
