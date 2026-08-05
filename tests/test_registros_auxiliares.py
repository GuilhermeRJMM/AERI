import unittest
from pathlib import Path

from backend.app.servicos.registros_auxiliares import (
    extrair_indice_registro_auxiliar,
    normalizar_busca,
)


class TesteRegistrosAuxiliares(unittest.TestCase):
    def test_extrai_pessoas_produto_safra_e_modalidade_do_texto(self):
        texto = """
        R.01-29.538 - PENHOR AGRÍCOLA. EMITENTE/DEVEDOR: João da Silva,
        brasileiro, agricultor, inscrito no CPF/MF sob o n.º 123.456.789-01.
        CREDORA: Cooperativa Agrícola Ltda., pessoa jurídica de direito privado,
        inscrita no CNPJ/MF sob o n.º 12.345.678/0001-90.
        Identificação do Produto: Soja em Grãos; Safra: 2026/2027.
        """

        indice = extrair_indice_registro_auxiliar(29538, texto)

        self.assertEqual(indice["modalidade"], "PENHOR")
        self.assertEqual(indice["produtos"], ["SOJA"])
        self.assertEqual(indice["safras"], ["2026/2027"])
        self.assertEqual([item["nome"] for item in indice["pessoas"]], ["João da Silva", "Cooperativa Agrícola Ltda."])
        self.assertIn("JOAO DA SILVA", indice["nomes_busca"])
        self.assertIn("12345678901", indice["documentos_busca"])
        self.assertEqual(len(indice["texto_hash"]), 64)

    def test_deduplica_produtos_safras_e_pessoas_repetidas(self):
        texto = """
        R.01 - ALIENAÇÃO DE SOJA, SAFRA 2025/2026.
        DEVEDOR: José Souza, inscrito no CPF sob o n.º 111.222.333-44.
        AV.02 - RETIFICAÇÃO DA ALIENAÇÃO DE SOJA, SAFRA 2025/2026.
        DEVEDOR: José Souza, inscrito no CPF sob o n.º 111.222.333-44.
        """

        indice = extrair_indice_registro_auxiliar(1, texto)

        self.assertEqual(indice["modalidade"], "ALIENAÇÃO")
        self.assertEqual(indice["produtos"], ["SOJA"])
        self.assertEqual(indice["safras"], ["2025/2026"])
        self.assertEqual(len(indice["pessoas"]), 1)

    def test_normaliza_busca_sem_acentos(self):
        self.assertEqual(normalizar_busca("  José   Agrícola  "), "JOSE AGRICOLA")

    def test_modalidade_considera_objeto_principal_e_safra_por_periodo_agricola(self):
        texto = """
        OBJETO DA GARANTIA: Em PENHOR CEDULAR DE PRIMEIRO GRAU, a colheita de Soja,
        período agrícola de setembro/2026 a maio/2027.
        NOTA: A Alienação Fiduciária integrante da mesma cédula foi registrada no Livro 2.
        """

        indice = extrair_indice_registro_auxiliar(29379, texto)

        self.assertEqual(indice["modalidade"], "PENHOR")
        self.assertEqual(indice["safras"], ["2026/2027"])

    def test_identifica_produtos_pecuarios(self):
        indice = extrair_indice_registro_auxiliar(
            29538,
            "OBJETO DA GARANTIA: Em PENHOR CEDULAR, 129 novilhos bovinos da raça nelore.",
        )

        self.assertEqual(indice["produtos"], ["BOVINOS", "NOVILHOS"])

    def test_migracao_cria_indice_sem_armazenar_texto_integral(self):
        sql = (Path(__file__).parents[1] / "backend/app/migrations/018_registros_auxiliares.sql").read_text(encoding="utf-8")

        self.assertIn("registros_auxiliares_aeri", sql)
        self.assertIn("texto_hash CHAR(64)", sql)
        self.assertIn("sincronizacao_registros_auxiliares_aeri", sql)
        self.assertNotIn("texto_integral", sql)


if __name__ == "__main__":
    unittest.main()
