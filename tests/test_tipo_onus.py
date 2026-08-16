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

    def test_matricula_33902_preserva_hipotecas_trasladadas_sem_duplicar_repactuacoes(self):
        texto = """
        AV.01-33.902 - TRASLADO/HIPOTECA. Na matrícula de origem encontra-se
        registrado o Aditivo de Re-Ratificação à Cédula Rural Hipotecária,
        que continua gravando este imóvel na sua totalidade, em PRIMEIRO GRAU.
        Vencimento: 31 de outubro de 2002. Forma de Pagamento: seis prestações.
        Objeto da Garantia: em hipoteca cedular de 1º grau, o imóvel desta matrícula.

        AV.02-33.902 - TRASLADO/HIPOTECA. Na matrícula de origem encontra-se
        registrado o Aditivo de Re-Ratificação à Cédula Rural Hipotecária,
        que continua gravando este imóvel na sua totalidade, em SEGUNDO GRAU.
        Vencimento: 31 de outubro de 2002. Forma de Pagamento: seis prestações.
        Objeto da Garantia: em hipoteca cedular de 2º grau, o imóvel desta matrícula.

        AV.04-33.902 - TRASLADO/HIPOTECA. Cédula Rural Pignoratícia e Hipotecária
        que continua gravando este imóvel na sua totalidade, em TERCEIRO GRAU.
        Objeto da Garantia: em hipoteca cedular de 3º grau, o imóvel desta matrícula.

        AV.09-33.902 - TRASLADO/REPACTUAÇÃO DE DÍVIDA A FAVOR DA UNIÃO.
        A repactuação refere-se à cédula da hipoteca de primeiro grau, que continua
        em vigor a favor da União, com novo vencimento e forma de pagamento. Fica
        suprimida a variação do preço mínimo básico do produto vinculado à operação.

        AV.10-33.902 - TRASLADO/REPACTUAÇÃO DE DÍVIDA A FAVOR DA UNIÃO.
        A repactuação refere-se à cédula da hipoteca de segundo grau, que continua
        em vigor a favor da União, com novo vencimento e forma de pagamento. Fica
        suprimida a variação do preço mínimo básico do produto vinculado à operação.
        """

        resultado = analisar_matricula(texto, numero_matricula="33902")
        atos = {ato["codigo"]: ato for ato in resultado["atos"]}

        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(set(atos), {"AV.01", "AV.02", "AV.04"})
        self.assertEqual(
            [atos[codigo]["grau_onus"] for codigo in ("AV.01", "AV.02", "AV.04")],
            ["1º grau", "2º grau", "3º grau"],
        )
        self.assertTrue(all(ato["status"] == "ATIVO" for ato in atos.values()))

    def test_sequestro_do_imovel_configura_onus(self):
        texto = """
        AV.17-123 - SEQUESTRO DO IMÓVEL. Nos termos do mandado judicial,
        procede-se ao sequestro do imóvel objeto desta matrícula.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(len(resultado["atos"]), 1)
        self.assertEqual(resultado["atos"][0]["categoria"], "ÔNUS")
        self.assertEqual(resultado["atos"][0]["tipo_onus"], "SEQUESTRO")
        self.assertEqual(resultado["atos"][0]["status"], "ATIVO")

    def test_vinculo_historico_por_cedula_configura_onus(self):
        texto = """
        MATRÍCULA 40. IMÓVEL: Fazenda Exemplo. PROPRIETÁRIO: Pessoa Teste.
        AV.01-40 - O imóvel acima está vinculado ao Banco do Brasil S/A,
        pela Cédula de 1º grau, emitida em 23/07/1975, vencível em 23/07/1976,
        inscrita sob o nº 3.507, fls. 192, Livro 9-E deste Cartório.
        """

        resultado = analisar_matricula(texto, numero_matricula="40")

        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(resultado["atos"][0]["categoria"], "ÔNUS")
        self.assertEqual(resultado["atos"][0]["tipo_onus"], "CÉDULA")
        self.assertEqual(resultado["atos"][0]["status"], "ATIVO")


if __name__ == "__main__":
    unittest.main()
