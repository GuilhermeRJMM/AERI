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

    def test_adquirentes_separados_por_ponto_e_virgula_e_e(self):
        cabecalho = """
        MATRÍCULA 23.209. PROPRIETÁRIA: MORRINHOS EMPREENDIMENTOS IMOBILIÁRIOS LTDA,
        inscrita no CNPJ sob o Nº14.042610/0001-62. TÍTULO AQUISITIVO: R-6-20.979.
        """
        registro = """
        R-2-23.209 - COMPRA E VENDA. o imóvel constante desta matrícula, foi adquirido por:
        RHAINER APARECIDO RIBEIRO, brasileiro, solteiro, funcionário de hotel,
        portador da CI. 5756564 SSP/GO e do CPF n.º 753.625.621-34, residente nesta Cidade;
        e, LOHAYNE MARIA OLIVEIRA SILVA, brasileira, solteira, caixa, portadora da CI.
        451176716 SSP/SP e do CPF nº 394.631.118-08, residente nesta Cidade; por compra feita
        a MORRINHOS EMPREENDIMENTOS IMOBILIÁRIOS LTDA-SPE, inscrita no CNPJ sob o
        Nº. 14.042.610/0001-62, pelo preço de R$ 66.000,00.
        """

        resultado = calcular_cadeia_dominial([SimpleNamespace(descricao=registro)], cabecalho + registro)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "RHAINER APARECIDO RIBEIRO": "50%",
                "LOHAYNE MARIA OLIVEIRA SILVA": "50%",
            },
        )

    def test_doacao_parcial_debita_somente_a_doadora_e_respeita_percentuais(self):
        inventario_victoria = """
        R.11-5.121 - INVENTÁRIO/PARTILHA - TRANSMITENTE: O Espólio de Paulo Tagliari,
        inscrito no CPF/MF sob o n.º 162.268.108-82. ADQUIRENTE: Victoria Teruel Ortiz
        Tagliari, inscrita no CPF/MF sob o n.º 255.472.868-26. IMÓVEL: 50% do imóvel.
        """
        inventario_osmar = """
        R.12-5.121 - INVENTÁRIO/PARTILHA - TRANSMITENTE: O Espólio de Paulo Tagliari,
        inscrito no CPF/MF sob o n.º 162.268.108-82. ADQUIRENTE: Osmar Tagliari,
        inscrito no CPF/MF sob o n.º 772.601.718-04. IMÓVEL: 12,50% do imóvel.
        """
        inventario_suely = """
        R.13-5.121 - INVENTÁRIO/PARTILHA - TRANSMITENTE: O Espólio de Paulo Tagliari,
        inscrito no CPF/MF sob o n.º 162.268.108-82. ADQUIRENTE: Suely Tagliari,
        inscrita no CPF/MF sob o n.º 095.788.998-40. IMÓVEL: 12,50% do imóvel.
        """
        doacao = """
        R.20-5.121 - DOAÇÃO. DOADORA: Victoria Teruel Ortiz Tagliari, inscrita no
        CPF/MF sob o n.º 255.472.868-26. DONATÁRIOS: 1)- Osmar Tagliari, inscrito no
        CPF/MF sob o n.º 772.601.718-04, equivalente a 12,5% do imóvel; 2)- Suely
        Tagliari, inscrita no CPF/MF sob o n.º 095.788.998-40, equivalente a 12,5%
        do imóvel; 3)- Fabio de Almeida Tagliari, inscrito no CPF/MF sob o n.º
        222.963.888-25, equivalente a 6,25% do imóvel; 4)- Fernanda de Almeida
        Tagliari, inscrita no CPF/MF sob o n.º 223.701.748-46, equivalente a 6,25%
        do imóvel; 5)- Paulo de Morais Tagliari Oliveira, inscrito no CPF/MF sob o
        n.º 423.074.468-42, equivalente a 6,25% do imóvel; 6)- Rebeca de Morais
        Teruel Tagliari Oliveira, inscrita no CPF/MF sob o n.º 423.074.478-14,
        equivalente a 6,25% do imóvel. IMÓVEL: equivalente a 50% do imóvel.
        """

        resultado = calcular_cadeia_dominial(
            [
                SimpleNamespace(descricao=inventario_victoria),
                SimpleNamespace(descricao=inventario_osmar),
                SimpleNamespace(descricao=inventario_suely),
                SimpleNamespace(descricao=doacao),
            ],
            inventario_victoria + inventario_osmar + inventario_suely + doacao,
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Osmar Tagliari": "25%",
                "Suely Tagliari": "25%",
                "Fabio de Almeida Tagliari": "6,25%",
                "Fernanda de Almeida Tagliari": "6,25%",
                "Paulo de Morais Tagliari Oliveira": "6,25%",
                "Rebeca de Morais Teruel Tagliari Oliveira": "6,25%",
            },
        )


if __name__ == "__main__":
    unittest.main()
