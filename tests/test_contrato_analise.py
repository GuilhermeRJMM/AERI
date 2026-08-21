import unittest

from backend.app.servicos.analise_matricula import analisar_matricula


class TesteContratoAnalise(unittest.TestCase):
    def test_contrato_e_versionado_e_nao_persiste_texto(self):
        resultado = analisar_matricula(
            "IMÓVEL: Lote 2 da quadra 3. PROPRIETÁRIO: JOÃO DA SILVA, CPF 123.456.789-09."
        )

        self.assertEqual("AERI Registral", resultado["meta"]["motor"])
        self.assertEqual("2.1.0", resultado["meta"]["versao"])
        self.assertEqual(64, len(resultado["meta"]["regras_hash"]))
        self.assertTrue(resultado["meta"]["versao_indice"].startswith("2.1.0+"))
        self.assertFalse(resultado["meta"]["texto_persistido"])
        self.assertEqual(64, len(resultado["resultado_hash"]))
        self.assertNotIn("texto", resultado)

    def test_campos_aplicaveis_urbanos_exibem_nao_consta(self):
        resultado = analisar_matricula(
            "IMÓVEL: Lote 2 da quadra 3, situado no Setor Central. "
            "PROPRIETÁRIO: JOÃO DA SILVA, CPF 123.456.789-09."
        )
        campos = resultado["imovel"]["campos_aplicaveis"]
        cadastros = {item["rotulo"]: item["valor"] for item in campos["cadastros"]}

        self.assertIn("Cadastro municipal / CCI", cadastros)
        self.assertIn("CEP", cadastros)
        self.assertEqual("NÃO CONSTA", cadastros["CEP"])

    def test_campos_rurais_nao_incluem_endereco_urbano(self):
        resultado = analisar_matricula(
            "IMÓVEL RURAL: Fazenda Boa Vista, com área de 10 ha. "
            "PROPRIETÁRIO: JOÃO DA SILVA, CPF 123.456.789-09."
        )
        campos = resultado["imovel"]["campos_aplicaveis"]
        rotulos = {item["rotulo"] for item in campos["identificacao"]}
        cadastros = {item["rotulo"]: item["valor"] for item in campos["cadastros"]}

        self.assertFalse({"Rua", "Número", "Setor"} & rotulos)
        self.assertIn("CAR", cadastros)
        self.assertIn("CCIR / Código rural", cadastros)


if __name__ == "__main__":
    unittest.main()
