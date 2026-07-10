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


    def test_adquirentes_numerados_sem_espaco_depois_do_hifen(self):
        registro = """
        R.04-38.801 - VENDA E COMPRA. ADQUIRENTES: 1)-Valter Alves da Silva Junior,
        brasileiro, divorciado, eletricista, inscrito no CPF/MF sob o n.º 806.115.831-00,
        residente em Morrinhos-GO, e 2)-Marcilia Alves de Oliveira, brasileira, solteira,
        agricultora, inscrita no CPF/MF sob o n.º 011.230.801-51, residente em Morrinhos-GO.
        IMÓVEL: 100,00% do imóvel descrito na matrícula.
        """

        resultado = calcular_cadeia_dominial([SimpleNamespace(descricao=registro)], registro)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Valter Alves da Silva Junior": "50%",
                "Marcilia Alves de Oliveira": "50%",
            },
        )


    def test_partilha_por_valor_e_vendas_parciais_com_cpf_repetido(self):
        compra_pedro = """
        R-02-3.154 - COMPRA E VENDA. o imovel objeto da presente matricula foi adquirido por
        Pedro Jorge Pinto, brasileiro, casado com Maria Madalena Pinto, CPF n. 016.806.681-53;
        por compra feita a Sebastiana Honorata de Lima; pelo preco de Cr$ 116.000,00.
        """
        meacao_pedro = """
        R-02-3.154 - PARTILHA. Nos termos do formal de partilha dos bens deixados por
        falecimento de Maria Madalena Pinto; coube ao viuvo meeiro Pedro Jorge Pinto,
        CPF n. 016.806.681-53; em pagamento de sua meacao; parte ideal de Cr$ 100.000,00,
        na avaliacao de Cr$ 200.000,00, sobre o imovel constante da presente matricula.
        """
        amarilda = """
        R-03-3.154 - PARTILHA. Nos termos do formal de partilha dos bens deixados por
        falecimento de Maria Madalena Pinto; coube a herdeira filha Amarilda Jorge da Cruz,
        CPF n. 016.806.681-53; em pagamento de sua heranca; parte ideal de Cr$ 33.333,30,
        na avaliacao de Cr$ 200.000,00, sobre o imovel constante da presente matricula.
        """
        ivone = """
        R-04-3.154 - PARTILHA. Nos termos do formal de partilha dos bens deixados por
        falecimento de Maria Madalena Pinto; coube a herdeira filha Ivone Aparecida Jorge,
        CPF n. 016.806.681-53; em pagamento de sua heranca; parte ideal de Cr$ 33.333,30,
        na avaliacao de Cr$ 200.000,00, sobre o imovel constante da presente matricula.
        """
        maria = """
        R-05-3.154 - PARTILHA. Nos termos do formal de partilha dos bens deixados por
        falecimento de Maria Madalena Pinto; coube a herdeira filha Maria Jose Jorge Alves,
        CPF n. 016.806.681-53; em pagamento de sua heranca; parte ideal de Cr$ 33.333,40,
        na avaliacao de Cr$ 200.000,00, sobre o imovel constante da presente matricula.
        """
        venda_jales = """
        R-07-3.154 - COMPRA E VENDA. Nos termos da escritura; Jales de Almeida Silverio,
        brasileiro, CPF n. 008.283.351-68; adquiriu por compra feita a Amarilda Jorge da Cruz
        Vaz e seu marido Nilson Fernandes Vaz; parte ideal de Cr$ 33.333,30, na avaliacao
        de Cr$ 200.000,00, sobre o imovel objeto da presente matricula.
        """
        venda_jaci_maria = """
        R-10-3.154 - COMPRA E VENDA. uma parte ideal de Cr$ 33.333,30, na avaliacao de
        Cr$ 200.000,00, sobre o imovel objeto da presente matricula, foi adquirido por
        JACI MOREIRA DE ARANTES, CPF n. 052.260.401-30; por compra feita a Maria Jose Jorge
        Alves Fernandes e seu esposo Sebastiao Fernandes Sobrinho.
        """
        venda_jaci_ivone = """
        R-11-3.154 - COMPRA E VENDA. uma parte ideal de Cr$ 33.333,30, na avaliacao de
        Cr$ 200.000,00, sobre o imovel objeto da presente matricula, foi adquirido por
        JACI MOREIRA DE ARANTES, CPF n. 052.260.401-30; por compra feita a Ivone Aparecida
        Jorge de Souza e seu marido Cleudson Rosa de Souza.
        """

        atos = [
            compra_pedro,
            meacao_pedro,
            amarilda,
            ivone,
            maria,
            venda_jales,
            venda_jaci_maria,
            venda_jaci_ivone,
        ]
        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=ato) for ato in atos],
            "\n".join(atos),
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Pedro Jorge Pinto": "50%",
                "Jales de Almeida Silverio": "16,66%",
                "JACI MOREIRA DE ARANTES": "33,34%",
            },
        )

    def test_partilha_com_parte_ideal_sem_de_e_adquiriu_com_virgula(self):
        cabecalho = """
        MATRÍCULA 5.210. Proprietário: Pedro Jorge Pinto, CPF nº 016.806.681-53,
        casado com Maria Madalena Pinto.
        """
        meacao = """
        R-01-5.210 - PARTILHA. coube ao viúvo meeiro Pedro Jorge Pinto,
        CPF nº 016.806.681-53; em pagamento de sua meação parte ideal cr$ 75.000,00,
        na avaliação de cr$ 150.000,00, sobre o imóvel constante da presente matrícula.
        """
        amarilda = """
        R-02-5.210 - PARTILHA. coube à herdeira filha Amarilda Jorge da Cruz,
        CPF nº 016.806.681-53; em pagamento de sua herança, parte ideal de cr$ 25.000,00,
        na avaliação de cr$ 150.000,00, sobre o imóvel constante da presente matrícula.
        """
        ivone = """
        R-03-5.210 - PARTILHA. coube à herdeira filha Ivone Aparecida Jorge,
        CPF nº 016.806.681-53; em pagamento de sua herança, parte ideal de cr$ 25.000,00,
        na avaliação de cr$ 150.000,00, sobre o imóvel constante da presente matrícula.
        """
        maria = """
        R-04-5.210 - PARTILHA. coube à herdeira filha Maria José Jorge Alves,
        CPF nº 016.806.681-53; em pagamento de sua herança, parte ideal de cr$ 25.000,00,
        na avaliação de cr$ 150.000,00, sobre o imóvel constante da presente matrícula.
        """
        venda_jales = """
        R-06-5.210 - COMPRA E VENDA. Nos termos da escritura pública; Jales de Almeida Silvério,
        brasileiro, CIC nº 008.283.351-68, adquiriu por compra feita a Amarilda Jorge da Cruz Vaz,
        parte correspondente a cr$ 25.000,00 na avaliação de cr$ 150.000,00, sobre o imóvel.
        """
        venda_jaci_maria = """
        R-10-5.210 - COMPRA E VENDA. uma parte ideal de Cr$ 25.000,00, na avaliação de Cr$150.000,00,
        no imóvel objeto da presente matrícula foi adquirido por JACI MOREIRA DE ARANTES,
        CPF nº 052.260.401-30; por compra feita a MARIA JOSÉ JORGE ALVES FERNANDES.
        """
        venda_jaci_ivone = """
        R-11-5.210 - COMPRA E VENDA. uma parte ideal de Cr$ 25.000,00, na avaliação de Cr$150.000,00,
        no imóvel objeto da presente matrícula foi adquirido por JACI MOREIRA DE ARANTES,
        CPF nº 052.260.401-30; por compra feita a Ivone Aparecida Jorge de Souza.
        """
        atos = [meacao, amarilda, ivone, maria, venda_jales, venda_jaci_maria, venda_jaci_ivone]

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=ato) for ato in atos],
            cabecalho + "\n".join(atos),
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Pedro Jorge Pinto": "50%",
                "Jales de Almeida Silvério": "16,66%",
                "JACI MOREIRA DE ARANTES": "33,34%",
            },
        )

    def test_venda_de_meacao_para_dois_adquirentes_antes_de_adquiriu(self):
        cabecalho = """
        MATRÍCULA 5.213. Proprietário: Pedro Jorge Pinto, CPF nº 016.806.681-53,
        casado com Maria Madalena Pinto.
        """
        meacao = """
        R-01-5.213 - PARTILHA. coube ao viúvo meeiro, Pedro Jorge Pinto,
        CPF nº 016.806.681-53; em pagamento de sua meação, parte ideal de cr$ 450.000,00,
        na qualificação de cr$ 900.000,00, sobre o imóvel constante da presente matrícula.
        """
        amarilda = """
        R-02-5.213 - PARTILHA. coube à herdeira filha Amarilda Jorge da Cruz,
        CPF nº 016.806.681-53; em pagamento de sua herança, parte ideal de cr$ 150.000,00,
        na avaliação de cr$ 900.000,00, sobre o imóvel constante da presente matrícula.
        """
        ivone = """
        R-03-5.213 - PARTILHA. coube à herdeira filha Ivone Aparecida Jorge,
        CPF nº 016.806.681-53; em pagamento de sua herança, parte ideal de cr$ 150.000,00,
        na avaliação de cr$ 900.000,00, sobre o imóvel constante da presente matrícula.
        """
        maria = """
        R-04-5.213 - PARTILHA. coube à herdeira filha Maria José Jorge Alves,
        CPF nº 016.806.681-53; em pagamento de sua herança, parte ideal de cr$ 150.000,00,
        na avaliação de cr$ 900.000,00, sobre o imóvel constante da presente matrícula.
        """
        venda_jales = """
        R-06-5.213 - COMPRA E VENDA. Nos termos da escritura; Jales de Almeida Silvério,
        CIC nº 008.283.351-68, adquiriu por compra feita a Amarilda Jorge da Cruz Vaz;
        parte ideal de cr$ 150.000,00 na avaliação de cr$ 900.000,00 sobre o imóvel.
        """
        venda_jose_pedro = """
        R-08-5.213 - COMPRA E VENDA. escritura lavrada pelo Tabelião local, no Lº 294,
        fl. 141, José Daniel da Silva Filho, brasileiro, comerciante, portador da CI nº
        546.989 e do CPF nº 169.250.761-34 e Pedro Daniel da Silva Sobrinho, brasileiro,
        divorciado, CPF nº 134.820.091-04; adquiriu por compra feita a Pedro Jorge Pinto;
        parte correspondente a cr$ 450.000,00, na avaliação de cr$ 900.000,00.
        """
        venda_jaci_maria = """
        R-11-5.213 - COMPRA E VENDA. uma parte ideal de Cr$ 150.000,00, na avaliação de
        Cr$900.000,00, sobre o imóvel objeto da presente matrícula foi adquirido por
        JACI MOREIRA DE ARANTES, CPF nº 052.260.401-30; por compra feita a MARIA JOSÉ
        JORGE ALVES FERNANDES.
        """
        venda_jaci_ivone = """
        R-12-5.213 - COMPRA E VENDA. uma parte ideal de Cr$ 150.000,00, na avaliação de
        Cr$900.000,00, sobre o imóvel objeto da presente matrícula foi adquirido por
        JACI MOREIRA DE ARANTES, CPF nº 052.260.401-30; por compra feita a Ivone Aparecida
        Jorge de Souza.
        """
        atos = [
            meacao,
            amarilda,
            ivone,
            maria,
            venda_jales,
            venda_jose_pedro,
            venda_jaci_maria,
            venda_jaci_ivone,
        ]

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=ato) for ato in atos],
            cabecalho + "\n".join(atos),
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "José Daniel da Silva Filho": "25%",
                "Pedro Daniel da Silva Sobrinho": "25%",
                "Jales de Almeida Silvério": "16,66%",
                "JACI MOREIRA DE ARANTES": "33,34%",
            },
        )


if __name__ == "__main__":
    unittest.main()
