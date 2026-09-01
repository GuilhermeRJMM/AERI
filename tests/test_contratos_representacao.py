import unittest

from backend.app.contratos_nucleo import extrator, minuta


class ContratosRepresentacaoTests(unittest.TestCase):
    def test_representante_e_cadeia_entram_automaticamente_na_minuta(self):
        texto = """
        CREDORA FIDUCIÁRIA: CAIXA ECONÔMICA FEDERAL, neste ato representada por
        ANA TESTE, nacionalidade brasileira, casada, nascida em 01/01/1980,
        economiária, portadora da carteira de identidade nº 4.379.715 expedida
        por DGPC/GO em 20/09/1999, CPF nº 003.381.471-60, endereço comercial na
        Avenida Central, nº 10, Goiânia-GO; conforme Procuração lavrada às
        folhas 120, do livro 500, em 10/08/2026, no 2º Ofício de Notas e
        Protesto de Brasília/DF. Agência responsável: Morrinhos.
        """

        ficha = extrator.extrai_do_texto(texto)

        self.assertEqual("ANA TESTE", ficha.credora.representante.nome)
        self.assertEqual(1, len(ficha.credora.procuracoes))
        ato = minuta.alienacao_fiduciaria(ficha)
        self.assertIn("representada no ato do contrato por Ana Teste", ato.texto)
        self.assertIn("Procuração lavrada em 10.08.2026", ato.texto)
        self.assertNotIn("[[falta: representante da CAIXA]]", ato.texto)
        self.assertNotIn("[[falta: procurações]]", ato.texto)


if __name__ == "__main__":
    unittest.main()
