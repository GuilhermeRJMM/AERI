import unittest
from types import SimpleNamespace

from backend.app.proprietarios import calcular_cadeia_dominial, extrair_bloco, extrair_pessoas


class TesteProprietarios(unittest.TestCase):
    def test_separa_esposa_expressamente_adquirente(self):
        descricao = """
        R.01-12.000 - Nos termos da escritura pública de compra e venda, o imóvel objeto
        da presente matrícula foi adquirido por José Colemar Rabelo, engenheiro civil,
        CI.SSP.GO n.º 510.009 e sua mulher Zilma de Fatima Ribeiro Rabelo, do lar,
        CI.SSP.GO n.º 1.567.469, ambos brasileiros, casados sob o regime da comunhão
        parcial de bens, portadores do CIC n.º 192.895.021-34; por compra feita a
        Jonas Alves Rabelo e sua mulher Floripa José Rabelo; pelo preço de R$ 13.000,00.
        """

        bloco = extrair_bloco(descricao, "ADQUIRENTE")
        pessoas = extrair_pessoas(bloco)

        self.assertEqual(
            [pessoa["nome"] for pessoa in pessoas],
            ["José Colemar Rabelo", "Zilma de Fatima Ribeiro Rabelo"],
        )

    def test_cadeia_dominial_mantem_os_dois_adquirentes(self):
        cabecalho = """
        MATRÍCULA 12.000. Proprietário: Jonas Alves Rabelo, brasileiro, casado com
        Floripa José Rabelo, portador do CIC 017.154.531-15. Título Aquisitivo: 28.134.
        """
        descricao = """
        R.01-12.000 - Nos termos da escritura pública de compra e venda, o imóvel objeto
        da presente matrícula foi adquirido por José Colemar Rabelo, engenheiro civil,
        CI.SSP.GO n.º 510.009 e sua mulher Zilma de Fatima Ribeiro Rabelo, do lar,
        CI.SSP.GO n.º 1.567.469, ambos brasileiros, casados sob o regime da comunhão
        parcial de bens, residentes nesta Cidade, portadores do CIC n.º 192.895.021-34;
        por compra feita a Jonas Alves Rabelo e sua mulher Floripa José Rabelo;
        pelo preço de R$ 13.000,00, sem condições.
        """
        ato = SimpleNamespace(descricao=descricao)

        resultado = calcular_cadeia_dominial([ato], cabecalho + "\n" + descricao)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "José Colemar Rabelo": "50%",
                "Zilma de Fatima Ribeiro Rabelo": "50%",
            },
        )

    def test_titulo_de_dominio_do_incra_transfere_ao_outorgado(self):
        cabecalho = """
        IMÓVEL: Fazenda Paraíso e Tijuqueiro, Lote 18. PROPRIETÁRIO: Instituto
        Nacional de Colonização e Reforma Agrária - INCRA, inscrita no CNPJ/MF
        sob o n.º 00.375.972/0001-60. Origem: Matrícula n.º 38.838.
        """
        registro = """
        R.05-39.071 - REFORMA AGRÁRIA. OUTORGANTE: Instituto Nacional de
        Colonização e Reforma Agrária - INCRA, inscrita no CNPJ/MF sob o n.º
        00.375.972/0001-60. OUTORGADO: Carlos Eli da Silva, brasileiro, solteiro,
        agricultor, inscrito no CPF/MF sob o n.º 211.721.881-49. IMÓVEL: O imóvel
        descrito na matrícula. FORMA DO TÍTULO: Título de Domínio emitido sob
        condição resolutiva pelo INCRA.
        """
        clausulas = """
        AV.06-39.071 - CLÁUSULAS RESOLUTIVAS E CONDIÇÕES. Nos termos do Título
        de Domínio, a transmissão foi feita sob condições resolutivas.
        """

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=registro), SimpleNamespace(descricao=clausulas)],
            cabecalho + registro + clausulas,
        )

        self.assertEqual(
            resultado,
            [{"nome": "Carlos Eli da Silva", "cpf": "211.721.881-49", "proporcao": "100%"}],
        )


if __name__ == "__main__":
    unittest.main()
