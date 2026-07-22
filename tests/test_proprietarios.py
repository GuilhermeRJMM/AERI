import unittest
from types import SimpleNamespace

from backend.app.parser import separar_atos
from backend.app.proprietarios import (
    calcular_cadeia_dominial,
    extrair_bloco,
    extrair_indicacao_titularidade,
    extrair_pessoas,
    extrair_proprietario_inicial,
    nomes_compativeis,
    parse_percent,
)


class TesteProprietarios(unittest.TestCase):
    def test_cabecalho_nao_e_cortado_por_referencia_ao_r01(self):
        texto = """
        MATRÍCULA 900. IMÓVEL: Lote 1. Título anterior R.01 da matrícula de origem.
        PROPRIETÁRIO: Pessoa Inicial, CPF 004.338.341-61.
        R.01-900 - COMPRA E VENDA. ADQUIRENTE: Pessoa Atual, CPF 111.222.333-44.
        IMÓVEL: A totalidade do imóvel.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["cpf"], "111.222.333-44")

    def test_aceita_erro_historico_proprietario_com_o_acentuado(self):
        pessoas = extrair_proprietario_inicial(
            "Próprietários: Pessoa Exemplo, CPF 004.338.341-61. O referido é verdade."
        )

        self.assertEqual(len(pessoas), 1)
        self.assertEqual(pessoas[0]["cpf"], "004.338.341-61")

    def test_aceita_erro_ocr_proprietarios_sem_p_inicial(self):
        pessoas = extrair_proprietario_inicial(
            "Roprietários: Pessoa Exemplo, CPF 004.338.341-61. Título aquisitivo: anterior."
        )

        self.assertEqual(len(pessoas), 1)
        self.assertEqual(pessoas[0]["cpf"], "004.338.341-61")

    def test_aceita_ponto_e_virgula_apos_rotulo_proprietario(self):
        pessoas = extrair_proprietario_inicial(
            "PROPRIETÁRIO; Pessoa Exemplo, CPF 004.338.341-61. Título aquisitivo: anterior."
        )

        self.assertEqual(len(pessoas), 1)

    def test_extrai_venderam_arrematante_e_usucapiao(self):
        casos = (
            (
                "Os proprietários venderam o imóvel para Pessoa Compradora, CPF 111.222.333-44, "
                "pelo valor de R$100.000,00.",
                "111.222.333-44",
            ),
            (
                "ARREMATAÇÃO. ARREMATANTE: Pessoa Arrematante, CPF 222.333.444-55. DOU FÉ.",
                "222.333.444-55",
            ),
            (
                "USUCAPIÃO. O domínio foi declarado em favor de: Pessoa Usucapiente, "
                "CPF 333.444.555-66. DOU FÉ.",
                "333.444.555-66",
            ),
        )

        for texto, documento in casos:
            with self.subTest(documento=documento):
                pessoas = extrair_pessoas(extrair_bloco(texto, "ADQUIRENTE"))
                self.assertEqual(len(pessoas), 1)
                self.assertEqual(pessoas[0]["cpf"], documento)

    def test_extrai_usucapientes_da_acao_promovida_em_desfavor(self):
        texto = (
            "R.02 - USUCAPIÃO. Sentença que julgou procedente a ação de usucapião "
            "promovida por Pessoa Usucapiente, CPF 333.444.555-66 e sua mulher "
            "Segunda Usucapiente, CPF 444.555.666-77, ambos brasileiros, em desfavor "
            "dos proprietários anteriores, conferindo-lhes o domínio do imóvel."
        )

        pessoas = extrair_pessoas(extrair_bloco(texto, "ADQUIRENTE"))

        self.assertEqual([pessoa["cpf"] for pessoa in pessoas], ["333.444.555-66", "444.555.666-77"])

    def test_extrai_comprador_com_rotulo_explicito(self):
        texto = (
            "R.01 - COMPRA E VENDA. COMPRADOR: Pessoa Compradora, brasileira, "
            "CPF 111.222.333-44. IMÓVEL: A totalidade do imóvel."
        )

        pessoas = extrair_pessoas(extrair_bloco(texto, "ADQUIRENTE"))

        self.assertEqual(len(pessoas), 1)
        self.assertEqual(pessoas[0]["cpf"], "111.222.333-44")

    def test_percentual_explicito_prevalece_sobre_valor_de_avaliacao(self):
        self.assertEqual(
            parse_percent(
                "IMÓVEL: parte ideal de 50% do imóvel, na avaliação de R$700.000,10."
            ),
            50.0,
        )

    def test_razao_monetaria_impossivel_nao_gera_percentual_acima_de_cem(self):
        self.assertEqual(
            parse_percent("parte ideal de R$50.000,00, na avaliação de R$1,00"),
            100.0,
        )

    def test_mesmo_cpf_prevalece_sobre_variacao_do_nome(self):
        texto = """
        MATRÍCULA 906. IMÓVEL: Lote 1.
        PROPRIETÁRIO: José da Silva Neto, CPF 004.338.341-61.
        R.01-906 - COMPRA E VENDA. TRANSMITENTE: J. da Silva, CPF 004.338.341-61.
        ADQUIRENTE: Pessoa Compradora, CPF 111.222.333-44.
        IMÓVEL: parte correspondente a 50%.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            {item["cpf"]: item["proporcao"] for item in resultado},
            {"004.338.341-61": "50%", "111.222.333-44": "50%"},
        )

    def test_pai_e_filho_nao_sao_o_mesmo_titular(self):
        self.assertFalse(
            nomes_compativeis("José Carlos da Silva", "José Carlos da Silva Filho")
        )

    def test_alteracao_de_nome_por_casamento_evitar_titular_duplicado(self):
        texto = """
        MATRÍCULA 908. IMÓVEL: Lote 1.
        PROPRIETÁRIOS: Luzia Agostinha da Silva, CPF 004.338.341-61; e
        Outra Pessoa, CPF 555.666.777-88.
        AV.01-908 - ALTERAÇÃO DO NOME POR CASAMENTO. Averba-se a alteração do
        nome da proprietária para Luzia Agostinha da Silva Souza, que passou a
        adotar depois de haver contraído matrimônio.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        por_nome = {item["nome"]: item["proporcao"] for item in resultado}
        self.assertEqual(len(resultado), 2)
        self.assertEqual(por_nome["Luzia Agostinha da Silva Souza"], "50%")
        self.assertEqual(por_nome["Outra Pessoa"], "50%")

    def test_transmissao_parcial_debita_unico_proprietario_mesmo_sem_rotulo_transmitente(self):
        texto = """
        MATRÍCULA 907. IMÓVEL: Lote 1.
        PROPRIETÁRIO: Pessoa Inicial, CPF 004.338.341-61.
        R.01-907 - COMPRA E VENDA. ADQUIRENTE: Pessoa Compradora, CPF 111.222.333-44.
        IMÓVEL: parte correspondente a 35%.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            {item["cpf"]: item["proporcao"] for item in resultado},
            {"004.338.341-61": "65%", "111.222.333-44": "35%"},
        )

    def test_proprietario_inicial_no_fim_do_cabecalho(self):
        texto = """
        MATRÍCULA 900. IMÓVEL: Lote n.º 01, Quadra 02, com área de 300m².
        PROPRIETÁRIO: João da Silva, brasileiro, inscrito no CPF sob o n.º 004.338.341-61.
        AV.01-900 - CÓDIGO DE ENDEREÇAMENTO POSTAL. O imóvel possui CEP n.º 75.650-000.
        """

        resultado = calcular_cadeia_dominial([], texto)

        self.assertEqual(
            resultado,
            [{"nome": "João da Silva", "cpf": "004.338.341-61", "proporcao": "100%"}],
        )

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

    def test_proprietario_inicial_com_conjuge_apos_regime_de_bens(self):
        cabecalho = """
        IMÓVEL: Lote n.º 33, da Quadra 12. PROPRIETÁRIO: Rodrigo Lafayette de Godoy,
        engenheiro, portador da Carteira de Identidade RG n.º 3435580-SSP/GO, e inscrito
        no CPF/MF n.º 805.212.901-04, casado sob o regime da comunhão parcial de bens
        posteriormente ao advento da Lei Federal 6.515/77 com Letícia Borges Mendanha de
        Godoy, psicóloga, portadora da Carteira Nacional de Habilitação CNH registro
        n.º 04164054414-DETRAN/GO, e inscrita no CPF/MF n.º 991.849.401-82, brasileiros,
        residentes e domiciliados em Morrinhos-GO. Origem: Matrícula n.º 21.369.
        """

        resultado = calcular_cadeia_dominial([], cabecalho)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Rodrigo Lafayette de Godoy",
                    "cpf": "805.212.901-04",
                    "proporcao": "100%",
                },
            ],
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


    def test_compra_com_redacao_vendeu_para(self):
        cabecalho = """
        MATRÍCULA 21.535. PROPRIETÁRIA: MARIA APARECIDA DA CUNHA, CPF nº 264.168.911-15.
        """
        venda = """
        R-2-Matr.21.535. COMPRA E VENDA. a proprietária, MARIA APARECIDA DA CUNHA,
        inscrita no CPF/MF sob o nº 264.168.911-15, vendeu o imóvel objeto desta matrícula
        para JACI MOREIRA DE ARANTES, inscrito no CPF/MF sob o nº 052.260.401-30,
        casado com MUIARI DAS GRAÇAS SERRA DE ARANTES; pelo valor de R$ 138.000,00.
        """

        resultado = calcular_cadeia_dominial([SimpleNamespace(descricao=venda)], cabecalho + venda)

        self.assertEqual(
            resultado,
            [{"nome": "JACI MOREIRA DE ARANTES", "cpf": "052.260.401-30", "proporcao": "100%"}],
        )

    def test_adjudicacao_transfere_propriedade(self):
        cabecalho = """
        MATRÍCULA 21.592. PROPRIETÁRIO: ROGÉRIO MARCONDES DE SOUZA SOARES,
        CPF nº 784.120.641-00.
        """
        adjudicacao = """
        R.07-21.592 - ADJUDICAÇÃO. para constar que o imóvel objeto desta matrícula
        coube ao adjudicante: Jaci Moreira de Arantes, inscrito no CPF/MF sob o nº
        052.260.401-30, casado com Muiari das Graças Serra de Arantes.
        """

        resultado = calcular_cadeia_dominial([SimpleNamespace(descricao=adjudicacao)], cabecalho + adjudicacao)

        self.assertEqual(
            resultado,
            [{"nome": "Jaci Moreira de Arantes", "cpf": "052.260.401-30", "proporcao": "100%"}],
        )

    def test_compra_com_redacao_adquirido_pelo_remove_titulo(self):
        cabecalho = """
        MATRICULA 5.975. Proprietario: Jose Ferreira de Melo, CPF n. 017.044.601-82.
        """
        venda = """
        R-01-5.975 - COMPRA E VENDA. o imovel objeto da presente matricula, foi adquirido pelo
        Dr. Jaci Moreira Arantes, brasileiro, medico, CIC n. 052.260.401-30; por compra feita a
        Jose Ferreira de Melo; pelo preco de Cr$ 68.900.000.
        """

        resultado = calcular_cadeia_dominial([SimpleNamespace(descricao=venda)], cabecalho + venda)

        self.assertEqual(
            resultado,
            [{"nome": "Jaci Moreira Arantes", "cpf": "052.260.401-30", "proporcao": "100%"}],
        )

    def test_indicacao_de_titularidade_extrai_percentuais_consolidados(self):
        indicacao = """
        AV.19-29.774 - INDICACAO DE TITULARIDADE EX-OFFICIO.
        ATO                                      CO-PROPRIETARIO                       PERCENTUAL
        Matricula, R.07, R.09, R.12, R.15       Divina Aparecida Amaro da Silva       31,71375%
        Matricula                               Albina Maria da Silva / Pedro Silva   9,49%
        Matricula, R.07,
        R.09
                                                 Teneciro da Cunha e Silva             0,84%
        Total                                   3 proprietarios                       42,04375%
        DOU FE.
        """

        proprietarios = extrair_indicacao_titularidade(indicacao)

        self.assertEqual(
            proprietarios,
            [
                {
                    "nome": "Divina Aparecida Amaro da Silva",
                    "cpf": "CPF/CNPJ NÃO INFORMADO",
                    "percentual": 31.71375,
                    "proporcao_texto": "31,71375%",
                },
                {
                    "nome": "Albina Maria da Silva / Pedro Silva",
                    "cpf": "CPF/CNPJ NÃO INFORMADO",
                    "percentual": 9.49,
                    "proporcao_texto": "9,49%",
                },
                {
                    "nome": "Teneciro da Cunha e Silva",
                    "cpf": "CPF/CNPJ NÃO INFORMADO",
                    "percentual": 0.84,
                    "proporcao_texto": "0,84%",
                },
            ],
        )

    def test_indicacao_de_titularidade_atualiza_cadeia_e_permite_ato_posterior(self):
        indicacao = """
        AV.19-29.774 - INDICACAO DE TITULARIDADE EX-OFFICIO.
        Matricula   Divina Aparecida Amaro da Silva   70%
        Matricula   Albina Maria da Silva             30%
        """
        venda = """
        R.20-29.774 - VENDA E COMPRA. TRANSMITENTE: Albina Maria da Silva.
        ADQUIRENTE: Comprador Novo, inscrito no CPF/MF sob o n. 111.222.333-44.
        IMOVEL: 30% do imovel descrito na matricula.
        """

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=indicacao), SimpleNamespace(descricao=venda)],
            indicacao + venda,
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Divina Aparecida Amaro da Silva": "70%",
                "Comprador Novo": "30%",
            },
        )

    def test_mencao_parcial_a_titularidade_nao_substitui_cadeia(self):
        texto = """
        AV.10 - INDICAÇÃO DE TITULARIDADE. O ato anterior menciona percentual
        de 6%, mas não contém tabela de co-proprietários.
        """

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=texto)],
            "MATRÍCULA 10. PROPRIETÁRIO: Pessoa Inicial, CPF 004.338.341-61." + texto,
        )

        self.assertEqual(resultado[0]["cpf"], "004.338.341-61")
        self.assertEqual(resultado[0]["proporcao"], "100%")

    def test_percentual_com_cifrao_antes_do_numero(self):
        self.assertEqual(
            parse_percent("coube à herdeira parte ideal de R$14% do imóvel"),
            14.0,
        )

    def test_percentual_de_multiplas_partes_por_valor(self):
        self.assertEqual(
            parse_percent(
                "três partes ideais de Cr$12.000,00 cada uma, na avaliação de Cr$72.000,00"
            ),
            50.0,
        )

    def test_percentual_soma_partes_ideais_com_valores_diferentes(self):
        texto = """
        adquiriu três partes ideais, sendo a primeira de Cr$200.000,00,
        a segunda de Cr$200.000,00 e a terceira de Cr$83.439,75,
        todas na avaliação de Cr$4.000.000,00.
        """
        self.assertAlmostEqual(parse_percent(texto), 12.08599375)

    def test_percentual_ignora_denominador_intermediario_da_parte(self):
        texto = """
        a primeira de Cr$116.560,25, na parte ideal de Cr$2.000.000,00;
        a segunda de Cr$397.599,57 na parte ideal de Cr$2.000.000,00;
        e a terceira de Cr$90.362,40 na parte ideal de Cr$2.000.000,00,
        todas na avaliação de Cr$4.000.000,00.
        """
        self.assertAlmostEqual(parse_percent(texto), 15.1130555)

    def test_percentual_soma_uma_e_outra_parte(self):
        texto = """
        duas partes ideais, sendo uma de Cr$94.880,52 e a outra Cr$31.626,84,
        ambas na avaliação de Cr$4.000.000,00.
        """
        self.assertAlmostEqual(parse_percent(texto), 3.162684)

    def test_percentual_soma_partes_repetidas_apos_primeira_avaliacao(self):
        texto = """
        parte ideal de Cr$465.892,12, remanescente da parte ideal de
        Cr$2.000.000,00, na avaliação de Cr$4.000.000,00; e parte ideal de
        Cr$200.000,00, na avaliação de Cr$4.000.000,00; e parte ideal de
        Cr$180.725,19, da parte ideal de Cr$2.000.000,00, na avaliação de
        Cr$4.000.000,00.
        """
        self.assertAlmostEqual(parse_percent(texto), 21.16543275)

    def test_percentual_por_valor_correspondente_em_moeda_convertida(self):
        texto = """
        uma parte de terras que corresponde o valor de Cz$180,72,
        na avaliação de Cz$4.000,00.
        """
        self.assertAlmostEqual(parse_percent(texto), 4.518)

    def test_percentual_fracao_avaliada_com_ordem_invertida(self):
        self.assertEqual(
            parse_percent(
                "imóvel avaliado por Cr$460.000,00, uma fração ideal de Cr$57.500,00"
            ),
            12.5,
        )

    def test_fracao_do_objeto_prevalece_sobre_percentual_final_dos_compradores(self):
        texto = """
        OBJETO: A parte ideal de 1/3 do imóvel total desta matrícula.
        Com a aquisição os dois adquirentes passaram a ser os únicos proprietários,
        na proporção de 50% para cada um.
        """
        self.assertAlmostEqual(parse_percent(texto), 100.0 / 3.0)

    def test_percentual_de_fracao_interna_com_ocr_monetario_historico(self):
        texto = """
        parte ideal de Cr$1.000.000,00 (um milhão), na avaliação de
        Cr$5.500,000, 00 na parte ideal de Cr$54.000.000,00 na avaliação de
        Cr$72.000.000,00, sobre o imóvel.
        """
        self.assertAlmostEqual(parse_percent(texto), 100.0 / 5.5 * 0.75)

    def test_percentual_de_fracao_interna_com_zero_duplicado_no_ocr(self):
        texto = """
        parte ideal de Cr$4.500.000,00, na avaliação de Cr$5.5000.000,00,
        na parte ideal de Cr$54.000.000,00, na avaliação de Cr$72.000.000,00.
        """
        self.assertAlmostEqual(parse_percent(texto), 4.5 / 5.5 * 75.0)

    def test_declaracao_de_unicos_proprietarios_consolida_adquirentes(self):
        texto = """
        MATRÍCULA 909. PROPRIETÁRIA: Pessoa Vendedora, CPF 004.338.341-61.
        R.01-909 - COMPRA E VENDA. TRANSMITENTE: Pessoa Vendedora,
        CPF 004.338.341-61. ADQUIRENTES: Pessoa Um, CPF 111.222.333-44; e
        Pessoa Dois, CPF 555.666.777-88. OBJETO: A parte ideal de 1/3 do imóvel.
        Com a aquisição os adquirentes passaram a ser os únicos proprietários do
        imóvel total, na proporção de 50% para cada um.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {"Pessoa Um": "50%", "Pessoa Dois": "50%"},
        )

    def test_percentual_solto_antes_de_do_imovel(self):
        self.assertEqual(parse_percent("foi transferido 24,10% do imóvel objeto"), 24.1)

    def test_percentual_com_extenso_entre_sinal_e_imovel(self):
        self.assertEqual(parse_percent("50% (cinquenta por cento) do imóvel"), 50.0)

    def test_fracao_monetaria_prevalece_sobre_usufruto_incidental(self):
        texto = (
            "parte ideal de CR$1.165.000,00 na avaliação de CR$6.400.000,00; "
            "condições: 50% do imóvel está clausulado com usufruto"
        )
        self.assertAlmostEqual(parse_percent(texto), 18.203125)

    def test_metade_do_imovel_equivale_a_cinquenta_por_cento(self):
        self.assertEqual(parse_percent("a metade do imóvel objeto da matrícula"), 50.0)

    def test_incorporacao_extrai_sociedade_e_socio_transmitente(self):
        texto = """
        R.47 - INCORPORAÇÃO DE BENS PARA INTEGRALIZAÇÃO DE CAPITAL. Para constar
        que 24,10% do imóvel foi incorporado ao patrimônio da sociedade empresária
        limitada AGROPECUÁRIA IRMÃOS CHIARI LTDA, inscrita no CNPJ/MF sob o n.º
        17.644.020/0001-06, com sede nesta cidade, por integralização feita pelo
        sócio José Renato Chiari, CPF/MF n.º 071.092.738-06, com plena anuência
        de seu cônjuge. O Capital Social será alterado. DOU FÉ.
        """

        adquirentes = extrair_pessoas(extrair_bloco(texto, "ADQUIRENTE"))
        transmitentes = extrair_pessoas(extrair_bloco(texto, "TRANSMITENTE"))

        self.assertEqual(adquirentes[0]["nome"], "AGROPECUÁRIA IRMÃOS CHIARI LTDA")
        self.assertEqual(adquirentes[0]["cpf"], "17.644.020/0001-06")
        self.assertEqual(transmitentes[0]["nome"], "José Renato Chiari")
        self.assertEqual(transmitentes[0]["cpf"], "071.092.738-06")

    def test_partilha_integral_em_atos_consecutivos_substitui_proprietario_anterior(self):
        cabecalho = "MATRÍCULA 210. PROPRIETÁRIO: Custódio Lopes de Souza, CPF 016.800.801-00."
        partilha_1 = """
        R.10-210 - Nos termos da Escritura Pública de Inventário e Partilha,
        lavrada em 21 de março de 2014; coube à viúva meeira Luzia Rosa de Souza,
        CPF 002.093.861-69, em pagamento de sua meação parte ideal de 50% do imóvel.
        """
        partilha_2 = """
        R.11-210 - Nos termos da Escritura Pública de Inventário e Partilha,
        lavrada em 21 de março de 2014; coube ao herdeiro Cleudson Rosa de Souza,
        CPF 539.215.006-30, em pagamento de sua herança parte ideal de 50% do imóvel.
        """

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=partilha_1), SimpleNamespace(descricao=partilha_2)],
            cabecalho + partilha_1 + partilha_2,
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {"Luzia Rosa de Souza": "50%", "Cleudson Rosa de Souza": "50%"},
        )

    def test_formal_de_partilha_por_valores_consolida_cem_por_cento(self):
        cabecalho = "MATRÍCULA 51. PROPRIETÁRIA: Odete Cândido de Castro, CPF 111.111.111-11."
        atos = [
            """R.03-51 - Formal de Partilha de 01 de abril de 2003 dos bens deixados por
            Odete Cândido de Castro; coube ao herdeiro Gilmar Alves Cândido, CPF
            161.050.111-68, parte ideal de R$19.317,52 na avaliação de R$73.150,00.""",
            """R.04-51 - Formal de Partilha de 01 de abril de 2003 dos bens deixados por
            Odete Cândido de Castro; coube ao herdeiro Silmar Alves Cândido, CPF
            342.031.841-00, parte ideal de R$19.317,52 na avaliação de R$73.150,00.""",
            """R.05-51 - Formal de Partilha de 01 de abril de 2003 dos bens deixados por
            Odete Cândido de Castro; coube à herdeira Lusmar Alves Cândido, CPF
            827.816.211-53, parte ideal de R$34.514,96 na avaliação de R$73.150,00.""",
        ]

        resultado = calcular_cadeia_dominial(
            [SimpleNamespace(descricao=texto) for texto in atos],
            cabecalho + "\n" + "\n".join(atos),
        )

        self.assertEqual(sum(float(item["proporcao"].replace(",", ".").rstrip("%")) for item in resultado), 100.0)
        self.assertEqual({item["nome"] for item in resultado}, {
            "Gilmar Alves Cândido", "Silmar Alves Cândido", "Lusmar Alves Cândido",
        })

    def test_partilha_historica_remove_qualificadores_separados_por_virgula(self):
        texto = """
        MATRÍCULA 789. PROPRIETÁRIO: Elias Gervásio Pereira, CPF 117.723.601-04.
        R.05-789 - Formal de Partilha de 28 de junho de 2005; coube ao viúvo meeiro,
        Elias Gervásio Pereira, CPF 117.723.601-04, em pagamento de sua meação 50% do imóvel.
        R.06-789 - Formal de Partilha de 28 de junho de 2005; coube ao herdeiro filho
        Elias Gervásio Pereira Júnior, em pagamento de sua herança 50% do imóvel.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {"Elias Gervásio Pereira": "50%", "Elias Gervásio Pereira Júnior": "50%"},
        )

    def test_proporcao_coletiva_divide_percentual_entre_nomes_do_grupo(self):
        texto = """
        MATRÍCULA 791. PROPRIETÁRIO: Pessoa Anterior, CPF 004.338.341-61.
        R.04-791 - COMPRA E VENDA. O imóvel foi adquirido por Heloisa Maria Romano
        de Melo, CPF 016.800.561-15; Gisele Maria Romano de Melo, CPF 217.012.101-34;
        Cláudio Romano de Melo, CPF 136.977.451-34 e Silvio Romano de Melo, solteiro,
        CPF 136.533.931-91; por compra feita ao proprietário anterior. O imóvel é
        adquirido na seguinte proporção: à Heloisa Maria Romano de Melo, parte
        correspondente a 50%; e à Gisele Maria Romano de Melo, Cláudio Romano de
        Melo e Silvio Romano de Melo, parte correspondente a 50%. O referido é verdade.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(len(resultado), 4)
        self.assertEqual(sum(float(item["proporcao"].replace(',', '.').rstrip('%')) for item in resultado), 100.0)
        self.assertEqual(next(item["proporcao"] for item in resultado if item["nome"].startswith("Heloisa")), "50%")

    def test_conjuge_apenas_qualificado_nao_e_adquirente_separado(self):
        bloco = (
            "2)- Éder Rodrigues da Silva, CPF 319.847.891-04, casado sob o regime "
            "da comunhão universal de bens com Maria Francisca Santana e Rodrigues, "
            "CPF 889.006.491-91, equivalente a 34,4769% do imóvel"
        )

        pessoas = extrair_pessoas(bloco)

        self.assertEqual([pessoa["nome"] for pessoa in pessoas], ["Éder Rodrigues da Silva"])
        self.assertEqual(pessoas[0]["percentual"], 34.4769)

    def test_intervenientes_anuentes_nao_entram_como_adquirentes(self):
        texto = (
            "R.10 - COMPRA E VENDA. ADQUIRENTE: Danielle Corcelli Gomes, "
            "CPF 003.393.721-41. INTERVENIENTES ANUENTES: José Alves Gomes, "
            "CPF 016.984.351-34, e Terezinha Cândida Gomes, CPF 010.070.691-63. "
            "IMÓVEL: 50% do imóvel."
        )

        pessoas = extrair_pessoas(extrair_bloco(texto, "ADQUIRENTE"))

        self.assertEqual([pessoa["nome"] for pessoa in pessoas], ["Danielle Corcelli Gomes"])

    def test_menores_coadquirentes_sao_separados_sem_incluir_representante(self):
        bloco = (
            "Diego Corcelli Gomes, menor impúbere, CI 4267870 e Danielle Corcelli "
            "Gomes, menor púbere, CI 4267920, ambos estudantes; neste ato o primeiro "
            "representado e a segunda assistida por Eliene Alves Gomes, CPF 491.306.921-72"
        )

        pessoas = extrair_pessoas(bloco)

        self.assertEqual([pessoa["nome"] for pessoa in pessoas], ["Diego Corcelli Gomes", "Danielle Corcelli Gomes"])

    def test_divorcio_com_outorgantes_reciprocos_preserva_coproprietario_estranho(self):
        texto = """
        MATRICULA 369. PROPRIETARIO: Pessoa Anterior, CPF 111.111.111-11.
        R.03-369 - COMPRA E VENDA. O imovel foi adquirido por: 1) Jose Daniel da
        Silva Filho, CPF 169.250.761-34; 2) Renato Antonio Fernandes, casado com
        Miriam Bittes Fernandes, CPF 262.920.846-04, por compra feita ao proprietario
        anterior, na proporcao de 50% para cada um.
        R.05-369 - Escritura publica de DIVORCIO DIRETO E PARTILHA DE BENS.
        Outorgantes e reciprocamente outorgados: Renato Antonio Fernandes e Miriam
        Bittes Fernandes. Fica dissolvida a sociedade conjugal e 50% do imovel
        fica pertencendo a Renato Antonio Fernandes, brasileiro, divorciado,
        CPF 262.920.846-04. O referido e verdade.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {"Jose Daniel da Silva Filho": "50%", "Renato Antonio Fernandes": "50%"},
        )
        self.assertEqual(
            next(item["cpf"] for item in resultado if item["nome"] == "Renato Antonio Fernandes"),
            "262.920.846-04",
        )

    def test_retificacao_compacta_preserva_sete_proprietarios_e_documentos(self):
        texto = """
        MATRICULA 39.802. IMOVEL: Fazenda Exemplo.
        PROPRIETARIOS: 1)- Osmar Tagliari, CPF 772.601.718-04, equivalente a 25%
        do imovel descrito na matricula; 2)- Suely Tagliari, CPF 095.788.998-40,
        equivalente a 25% do imovel descrito na matricula; 3)- Fabio de Almeida
        Tagliari, CPF 222.963.888-25, equivalente a 12,5% do imovel descrito na
        matricula; 4)- Fernanda de Almeida Tagliari, CPF 223.701.748-46,
        equivalente a 12,5% do imovel descrito na matricula; 5)- Paulo de Morais
        Tagliari Oliveira, CPF 423.074.468-42, equivalente a 10,42% do imovel;
        6)- Rebeca de Morais Teruel Tagliari Oliveira, CPF 423.074.478-14,
        equivalente a 6,25% do imovel; 7)- Paulo Donizete Oliveira,
        CPF 073.223.588-05, equivalente a 4,16% do imovel. ORIGEM: Matricula 5.121.
        AV.04-39.802 - RETIFICACAO E INDICACAO DE TITULARIDADE EX-OFFICIO.
        CO-PROPRIETARIOPERCENTUAL (%)CORRESPONDENCIA NA AREA DO IMOVEL (EM HECTARES)
        Osmar Tagliari25%11,6642haSuely Tagliari25%11,6642haFabio de Almeida
        Tagliari12,50%5,8321haFernanda de Almeida Tagliari12,50%5,8321haPaulo
        de Morais Tagliari Oliveira10,42%4,8616haRebeca de Morais Teruel Tagliari
        Oliveira10,42%4,8616haPaulo Donizete Oliveira4,16%1,9410ha07 proprietarios100%46,6568ha
        DOU FE.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(len(resultado), 7)
        self.assertEqual(
            sum(float(item["proporcao"].replace(",", ".").rstrip("%")) for item in resultado),
            100.0,
        )
        rebeca = next(item for item in resultado if item["nome"].startswith("Rebeca"))
        osmar = next(item for item in resultado if item["nome"] == "Osmar Tagliari")
        self.assertEqual(rebeca["proporcao"], "10,42%")
        self.assertEqual(osmar["cpf"], "772.601.718-04")

    def test_percentual_sem_virgula_por_ocr_e_numeracao_sem_parentese(self):
        bloco = (
            "1- Valtemir Jose de Oliveira, CPF 333.266.571-53, parte correspondente "
            "a 8562%; e 2-Laurentina Dias de Oliveira, CPF 291.965.661-91, parte "
            "correspondente a 14,38%"
        )

        pessoas = extrair_pessoas(bloco)

        self.assertEqual([item["nome"] for item in pessoas], [
            "Valtemir Jose de Oliveira", "Laurentina Dias de Oliveira",
        ])
        self.assertEqual([item["percentual"] for item in pessoas], [85.62, 14.38])
        self.assertEqual(parse_percent("parte correspondente a 8562% do imovel"), 85.62)

    def test_coube_com_acento_agudo_incorreto_extrai_herdeira(self):
        ato = (
            "FORMAL DE PARTILHA. coube á herdeira filha Edelma Maria Cardoso, "
            "CPF 307.511.441-34, em pagamento de sua heranca, parte ideal de 6,25%."
        )

        pessoas = extrair_pessoas(extrair_bloco(ato, "ADQUIRENTE"))

        self.assertEqual(pessoas[0]["nome"], "Edelma Maria Cardoso")
        self.assertEqual(pessoas[0]["cpf"], "307.511.441-34")

    def test_partilha_residual_nao_reduz_adquirente_que_ja_consta_integral(self):
        texto = """
        MATRICULA 13.431. PROPRIETARIO: Jales Moreira da Silva, CPF 016.756.561-34.
        R.03-13.431 - COMPRA E VENDA. Escritura lavrada pelo tabelionato local,
        Carlos Humberto da Silva, CPF 278.142.031-04; adquiriu por compra feita a
        Jales Moreira da Silva o imovel objeto da matricula.
        R.10-13.431 - INVENTARIO/PARTILHA. TRANSMITENTE: O Espolio de Jales Moreira
        da Silva, CPF 016.756.561-34. ADQUIRENTE: Carlos Humberto da Silva,
        CPF 278.142.031-04. IMOVEL: A proporcao de 16,26% do imovel.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(resultado, [{
            "nome": "Carlos Humberto da Silva",
            "cpf": "278.142.031-04",
            "proporcao": "100%",
        }])


if __name__ == "__main__":
    unittest.main()
