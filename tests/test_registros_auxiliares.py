import unittest
from pathlib import Path

from backend.app.servicos.registros_auxiliares import (
    extrair_indice_registro_auxiliar,
    normalizar_busca,
    resumo_certidao_registro_auxiliar,
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
        self.assertEqual([item["nome"] for item in indice["pessoas"]], ["João da Silva"])
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

    def test_ignora_conjuge_credor_avalista_e_demais_qualificados(self):
        texto = """
        EMITENTE/DEVEDOR: João da Silva, agricultor, inscrito no CPF/MF sob o n.º
        123.456.789-01, casado com Maria da Silva, inscrita no CPF/MF sob o n.º
        222.333.444-55. AVALISTA: Pedro Souza, inscrito no CPF sob o n.º 333.444.555-66.
        CREDORA: Banco Exemplo S.A., inscrito no CNPJ sob o n.º 12.345.678/0001-90.
        """

        indice = extrair_indice_registro_auxiliar(10, texto)

        self.assertEqual(len(indice["pessoas"]), 1)
        self.assertEqual(indice["pessoas"][0]["nome"], "João da Silva")
        self.assertNotIn("MARIA", indice["nomes_busca"])
        self.assertNotIn("PEDRO", indice["nomes_busca"])
        self.assertNotIn("BANCO", indice["nomes_busca"])

    def test_preserva_varios_devedores_quando_cabecalho_e_plural(self):
        texto = """
        DEVEDORES: 1)- Ana Souza, inscrita no CPF sob o n.º 111.222.333-44;
        2)- Carlos Souza, inscrito no CPF sob o n.º 555.666.777-88.
        CREDORA: Cooperativa Exemplo, inscrita no CNPJ sob o n.º 12.345.678/0001-90.
        """

        indice = extrair_indice_registro_auxiliar(11, texto)

        self.assertEqual([item["nome"] for item in indice["pessoas"]], ["Ana Souza", "Carlos Souza"])

    def test_preserva_varios_devedores_mesmo_com_cabecalho_singular(self):
        # Regressão: matrícula 29.461 (relato de busca por "PAULO CESAR
        # CHIARI" faltando no resultado) tinha rótulo "DEVEDOR:" no singular
        # listando duas pessoas — a segunda ficava de fora porque a divisão
        # em pessoas dependia do cabeçalho sinalizar plural explicitamente.
        texto = """
        DEVEDOR: 1)- João da Silva, inscrito no CPF sob o n.º 111.222.333-44;
        2)- Paulo Cesar Chiari, inscrito no CPF sob o n.º 555.666.777-88.
        CREDORA: Cooperativa Exemplo, inscrita no CNPJ sob o n.º 12.345.678/0001-90.
        """

        indice = extrair_indice_registro_auxiliar(29461, texto)

        self.assertEqual(
            [item["nome"] for item in indice["pessoas"]],
            ["João da Silva", "Paulo Cesar Chiari"],
        )

    def test_reconhece_emitente_com_papeis_complementares(self):
        casos = (
            "EMITENTE/DEVEDOR/FIEL",
            "EMITENTE/DEVEDOR/FIEL DEPOSITÁRIO",
            "EMITENTES/DEVEDORES/FIÉIS DEPOSITÁRIOS",
            "EMITENTE/DEVEDOR/DEPOSITÁRIO",
            "EMITENTE/FIEL",
            "EMITENTE/DEPOSITÁRIO",
        )
        for papel in casos:
            with self.subTest(papel=papel):
                texto = (
                    f"{papel}: João da Silva, inscrito no CPF sob o n.º "
                    "123.456.789-01. CREDOR: Banco Exemplo S.A."
                )
                pessoas = extrair_indice_registro_auxiliar(15, texto)["pessoas"]
                self.assertEqual([item["nome"] for item in pessoas], ["João da Silva"])

    def test_reconhece_cabecalho_maiusculo_sem_dois_pontos(self):
        texto = """
        EMITENTE/DEVEDOR/FIEL João da Silva, inscrito no CPF sob o n.º
        123.456.789-01. CREDOR Banco Exemplo S.A., inscrito no CNPJ sob o n.º
        12.345.678/0001-90.
        """

        pessoas = extrair_indice_registro_auxiliar(17, texto)["pessoas"]

        self.assertEqual([item["nome"] for item in pessoas], ["João da Silva"])

    def test_reconhece_notacao_parentetica_de_multiplos_emitentes(self):
        texto = """
        EMITENTE(S)/DEVEDOR(ES)/FIEL(IS): 1)- Ana Souza, inscrita no CPF sob o
        n.º 111.222.333-44; 2)- Carlos Souza, inscrito no CPF sob o n.º
        555.666.777-88. CREDORA: Cooperativa Exemplo.
        """

        pessoas = extrair_indice_registro_auxiliar(16, texto)["pessoas"]

        self.assertEqual([item["nome"] for item in pessoas], ["Ana Souza", "Carlos Souza"])

    def test_endereco_com_dois_pontos_nao_interrompe_antes_do_documento(self):
        texto = """
        EMITENTE E DEVEDORA: Ana Souza, brasileira, com endereço: Rua Um,
        inscrita no CPF sob o n.º 111.222.333-44. Credor: Banco Exemplo S.A.,
        inscrito no CNPJ sob o n.º 12.345.678/0001-90.
        """

        indice = extrair_indice_registro_auxiliar(12, texto)

        self.assertEqual(len(indice["pessoas"]), 1)
        self.assertEqual(indice["pessoas"][0]["nome"], "Ana Souza")

    def test_situacao_permanece_ativa_sem_cancelamento_integral(self):
        texto = """
        R.01 - PENHOR. EMITENTE/DEVEDOR: João da Silva, inscrito no CPF sob o
        n.º 123.456.789-01. O emitente não poderá cancelar unilateralmente a cédula.
        AV.02 - LIBERAÇÃO PARCIAL DE BENS.
        """

        self.assertEqual(extrair_indice_registro_auxiliar(13, texto)["situacao"], "ATIVO")

    def test_cancelamento_integral_baixa_registro_auxiliar(self):
        texto = """
        R.01 - PENHOR. EMITENTE/DEVEDOR: João da Silva, inscrito no CPF sob o
        n.º 123.456.789-01. AV.02 - CANCELAMENTO DO PENHOR. Fica cancelado o R.01.
        """

        self.assertEqual(extrair_indice_registro_auxiliar(14, texto)["situacao"], "BAIXADO")

    def test_calcula_resultado_e_valor_da_certidao(self):
        self.assertEqual(
            resumo_certidao_registro_auxiliar(0),
            {"resultado": "NEGATIVA", "quantidadeRegistros": 0, "valorCertidao": "139.93"},
        )
        self.assertEqual(
            resumo_certidao_registro_auxiliar(1),
            {"resultado": "POSITIVA", "quantidadeRegistros": 1, "valorCertidao": "139.93"},
        )
        self.assertEqual(
            resumo_certidao_registro_auxiliar(4),
            {"resultado": "POSITIVA", "quantidadeRegistros": 4, "valorCertidao": "559.72"},
        )

    def test_migracao_cria_indice_sem_armazenar_texto_integral(self):
        sql = (Path(__file__).parents[1] / "backend/app/migrations/018_registros_auxiliares.sql").read_text(encoding="utf-8")

        self.assertIn("registros_auxiliares_aeri", sql)
        self.assertIn("texto_hash CHAR(64)", sql)
        self.assertIn("sincronizacao_registros_auxiliares_aeri", sql)
        self.assertNotIn("texto_integral", sql)

    def test_reindexacao_nao_apaga_indice_existente(self):
        sql = (Path(__file__).parents[1] / "backend/app/migrations/019_reindexar_emitentes_devedores.sql").read_text(encoding="utf-8")

        self.assertNotIn("DELETE FROM registros_auxiliares_aeri", sql)


if __name__ == "__main__":
    unittest.main()
