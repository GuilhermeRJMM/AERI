import unittest

from backend.app.dados_imovel import extrair_dados_imovel


class DadosImovelTests(unittest.TestCase):
    def test_urbano_extrai_dados_e_aplica_retificacao_ex_officio(self):
        texto = """
        MATRÍCULA 23.209 - MORRINHOS. IMÓVEL: Rua Casimiro Luiz Ferreira,
        Lugar denominado Cordeiro, Residencial Antônio Corrêa Bueno, nesta Cidade,
        constituído de: Lote de terras Nº12, da quadra 06, com a área de 250,00m2,
        sendo: 10,00 metros de frente pela dita Rua; 25,00 metros de extensão do lado
        direito, confrontando com lote 11; 25,00 metros de extensão do lado esquerdo,
        confrontando com o lote 13; e, nos fundos 10,00 metros de largura,
        confrontando com o lote 19; Cadastrado na Prefeitura sob o Nº06/12-C.
        PROPRIETÁRIA: MORRINHOS EMPREENDIMENTOS IMOBILIÁRIOS LTDA.
        ----------------------------------------------------------------------------
        AV.05-23.209 - RETIFICAÇÃO EX-OFFICIO. passa a constar corretamente que
        o mesmo confronta com 10,00m de largura na frente e nos fundos por 25,00m
        de extensão nas laterais, dividindo na frente com a citada rua; fundos com
        o lote n.º 19; lateral direita com o lote n.º 13; e, lateral esquerda com
        o lote n.º 11.
        """

        dados = extrair_dados_imovel(
            texto,
            [
                {"nome": "RHAINER APARECIDO RIBEIRO"},
                {"nome": "LOHAYNE MARIA OLIVEIRA SILVA"},
            ],
        )

        self.assertEqual(dados["tipo"], "urbano")
        self.assertEqual(dados["matricula"], "23.209")
        self.assertEqual(dados["lote"], "12")
        self.assertEqual(dados["quadra"], "06")
        self.assertEqual(dados["area"], "250,00 m²")
        self.assertEqual(dados["cci"], "06/12-C")
        self.assertEqual(dados["setor"], "Residencial Antônio Corrêa Bueno")
        self.assertEqual(
            dados["proprietario"],
            "RHAINER APARECIDO RIBEIRO; LOHAYNE MARIA OLIVEIRA SILVA",
        )
        self.assertEqual(dados["confrontacoes"]["lateral_direita"], "o lote n.º 13")
        self.assertEqual(dados["confrontacoes"]["lateral_esquerda"], "o lote n.º 11")

    def test_rural_extrai_identificadores_principais(self):
        texto = """
        MATRÍCULA 39.071. IMÓVEL: Fazenda Paraíso e Tijuqueiro, com a área de
        13,9345ha. INCRA/CCIR nº 950.157.123.456-7. ITR/NIRF nº 1.234.567-8.
        CAR nº GO-5213806-ABCDEF1234567890ABCDEF1234567890.
        """

        dados = extrair_dados_imovel(texto)

        self.assertEqual(dados["tipo"], "rural")
        self.assertEqual(dados["matricula"], "39.071")
        self.assertEqual(dados["nome"], "Fazenda Paraíso e Tijuqueiro")
        self.assertEqual(dados["area"], "13,9345 ha")
        self.assertEqual(dados["incra_ccir"], "950.157.123.456-7")
        self.assertEqual(dados["itr_cib_nirf"], "1.234.567-8")
        self.assertEqual(dados["car"], "GO-5213806-ABCDEF1234567890ABCDEF1234567890")


if __name__ == "__main__":
    unittest.main()
