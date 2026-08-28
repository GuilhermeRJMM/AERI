from types import SimpleNamespace
import unittest

from backend.app.proprietarios import (
    calcular_cadeia_dominial,
    extrair_indicacao_titularidade,
    extrair_proprietario_inicial,
    nomes_compativeis,
    parse_percent,
)
from backend.app.analise.onus import processar_atos


def ato(descricao):
    return SimpleNamespace(descricao=descricao)


class CorrecoesAuditoriaCadeiaTest(unittest.TestCase):
    def test_matricula_18315_clausula_financeira_nao_oculta_compradores(self):
        texto = (
            "MATRÍCULA 18.315. IMÓVEL: lote. PROPRIETÁRIO: Município de "
            "Morrinhos, CNPJ 01.789.551/0001-49.\n"
            "R-1-18.315- DOAÇÃO. O imóvel objeto da presente matrícula foi "
            "adquirido por EDION ARANTES DO CARMO, CPF 509.327.561-15, por "
            "doação que lhe fez o Município de Morrinhos.\n"
            "R-3-18.315- CONTRATO POR INSTRUMENTO PARTICULAR DE COMPRA E VENDA "
            "DE UNIDADE ISOLADA E MÚTUO. O imóvel constante desta matrícula "
            "foi adquirido por KENIA CANDIDA DOS SANTOS, CPF 019.045.691-45; "
            "e LUZIANO NUNES DOS SANTOS, CPF 976.867.941-72; por compra feita "
            "a EDION ARANTES DO CARMO, CPF 509.327.561-15, pelo preço de "
            "R$40.000,00, sendo: Recursos da conta vinculada do FGTS dos "
            "Compradores: R$2.300,00. Financiamento: R$34.700,00."
        )

        resultado = calcular_cadeia_dominial(processar_atos(texto), texto)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "KENIA CANDIDA DOS SANTOS": "50%",
                "LUZIANO NUNES DOS SANTOS": "50%",
            },
        )

    def test_grafia_historica_wilsom_e_wilson_identifica_mesma_pessoa(self):
        self.assertTrue(
            nomes_compativeis('Wilsom Alves da Costa', 'Wilson Alves da Costa')
        )

    def test_cabecalho_aceita_prorietarios_com_erro_historico(self):
        texto = (
            "MATRÍCULA 7.388. PRORIETÁRIOS: 1) Pedro Nunes de Azeredo, CPF "
            "017.213.131-68; 2) Maria de Lourdes Nunes Azeredo Costa, CPF "
            "017.285.711-20. TÍTULO AQUISITIVO: registro anterior."
        )

        resultado = extrair_proprietario_inicial(texto)

        self.assertEqual(
            [item["nome"] for item in resultado],
            ["Pedro Nunes de Azeredo", "Maria de Lourdes Nunes Azeredo Costa"],
        )

    def test_cabecalho_plural_separa_nome_com_particulas_e_preserva_cpf(self):
        texto = (
            "MATRÍCULA 3.036. PROPRIETÁRIOS: Aparecida Olímpia de Azeredo "
            "Souza, CPF 003.441.091-00; Maria de Lourdes Nunes Azeredo Costa, "
            "CPF 017.285.711-20; Lucicilio Frauzino Pereira, CI 6.312 e CPF "
            "016.639.171-91, residente nesta cidade e Hugo Frauzino Pereira, "
            "CPF 016.584.681-04. ORIGEM: registro anterior."
        )

        resultado = extrair_proprietario_inicial(texto)

        self.assertEqual(
            [(item["nome"], item["cpf"]) for item in resultado],
            [
                ("Aparecida Olímpia de Azeredo Souza", "003.441.091-00"),
                ("Maria de Lourdes Nunes Azeredo Costa", "017.285.711-20"),
                ("Lucicilio Frauzino Pereira", "016.639.171-91"),
                ("Hugo Frauzino Pereira", "016.584.681-04"),
            ],
        )

    def test_indicacao_compacta_separa_decimal_percentual_e_area(self):
        descricao = (
            "INDICAÇÃO RELAÇÃO TITULARIDADE. "
            "ATOCO-PROPRIETÁRIO EQUIV.DECIMAL PERCENTUAL (%)"
            "CORRESPONDÊNCIA NA ÁREA DO IMÓVEL (EM HECTARES)"
            "R.12 e R.22Alessandro Malvezzi0,416741,6720,1214ha"
            "R.12 e R.23Andreia Malvezzi Rossi0,583358,33%28,1700ha"
            "Total1100%48,2914ha"
        )

        resultado = extrair_indicacao_titularidade(descricao)

        self.assertEqual(
            [(item["nome"], item["proporcao_texto"]) for item in resultado],
            [
                ("Alessandro Malvezzi", "41,67%"),
                ("Andreia Malvezzi Rossi", "58,33%"),
            ],
        )

    def test_fracao_numerica_direta_do_imovel(self):
        descricao = (
            "COMPRA E VENDA. 2/11 (dois onze avos) do imóvel objeto da "
            "presente matrícula foi adquirido pelo comprador."
        )

        self.assertAlmostEqual(parse_percent(descricao), 2 / 11 * 100)

    def test_fracao_numerica_sobre_o_imovel(self):
        descricao = (
            "SOBREPARTILHA. Coube à viúva meeira, em pagamento de sua meação "
            "e cessão, parte correspondente a 1/5 sobre o imóvel constante "
            "da presente matrícula."
        )

        self.assertAlmostEqual(parse_percent(descricao), 20.0)

    def test_usucapiao_com_virgula_antes_de_promovida(self):
        descricao = (
            "USUCAPIÃO. A ação de usucapião, promovida por Abadio Pio da Costa, "
            "CPF 016.778.371-87, conferiu-lhe o domínio do imóvel constante da "
            "presente matrícula."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(resultado[0]["nome"], "Abadio Pio da Costa")

    def test_adquirida_pela_pessoa_juridica(self):
        descricao = (
            "DOAÇÃO. O imóvel objeto da presente matrícula foi adquirida pela "
            "Companhia de Habitação de Goiás COHAB-GO, CNPJ 01.274.240/0001-47, "
            "por doação que lhe fez o Município."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Companhia de Habitação de Goiás COHAB-GO",
                    "cpf": "01.274.240/0001-47",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )

    def test_divisao_com_coube_exclusivamente(self):
        descricao = (
            "AÇÃO DE DIVISÃO. Coube exclusivamente à condômina Itelvina Pires "
            "da Costa, CPF 100.970.083-91, o quinhão constante da presente "
            "matrícula, no valor de Cr$29.000,00."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(resultado[0]["nome"], "Itelvina Pires da Costa")

    def test_desmembramento_por_divisao_retira_titular_do_remanescente(self):
        atos = [
            ato(
                "COMPRA E VENDA. ADQUIRENTES: Ana Silva, CPF 111.111.111-11, "
                "na proporção de 60%; Bruno Silva, CPF 222.222.222-22, na "
                "proporção de 40%. IMÓVEL: 100% do imóvel."
            ),
            ato(
                "MATRÍCULA. Em virtude de divisão, desmembrou-se desta "
                "matrícula uma gleba de terras, que foi matriculada sob o nº "
                "14.432, pertencente a Ana Silva. O referido é verdade e dou fé."
            ),
        ]

        resultado = calcular_cadeia_dominial(atos)

        self.assertEqual(
            resultado,
            [{
                "nome": "Bruno Silva",
                "cpf": "222.222.222-22",
                "proporcao": "100%",
                "proporcao_incerta": False,
            }],
        )

    def test_divisao_que_abre_sucessoras_nao_recredita_beneficiarios(self):
        atos = [
            ato(
                "COMPRA E VENDA. ADQUIRENTES: Ana Silva, CPF 111.111.111-11; "
                "Bruno Silva, CPF 222.222.222-22. IMÓVEL: 100% do imóvel."
            ),
            ato(
                "DIVISÃO AMIGÁVEL. O imóvel foi dividido em duas glebas: "
                "a primeira, matriculada sob o nº 21.522, atribuída a Ana Silva; "
                "a segunda, matriculada sob o nº 21.523, atribuída a Carla "
                "Souza; ficando em consequência encerrada esta matrícula."
            ),
        ]

        resultado = calcular_cadeia_dominial(atos)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {"Ana Silva": "50%", "Bruno Silva": "50%"},
        )

    def test_divisao_encerrada_confere_titulares_pelas_areas_sucessoras(self):
        atos = [
            ato(
                "COMPRA E VENDA. ADQUIRENTES: Rosana das Graças Garcia Naves; "
                "Réginer Aparecida Garcia Naves; Rosidelma Garcia Naves; "
                "Rogério Marcos Garcia Naves; Vivaldo de Souza Machado. "
                "IMÓVEL: 100% do imóvel."
            ),
            ato(
                "DIVISÃO AMIGÁVEL. O imóvel foi dividido em 04 lotes: a 1ª "
                "com a área de 71,89,09 ha; matriculada sob o nº 21.522, "
                "atribuída à Rosana das Graças Garcia Naves, Réginer Aparecida "
                "Garcia Naves, Rosidelma Garcia Naves e Rogério Marcos Garcia "
                "Naves; a 2ª com a área de 11,98,18 ha; matriculada sob o nº "
                "21.523, atribuída à Rosana das Graças Garcia Naves, Réginer "
                "Aparecida Garcia Naves, Rosidelma Garcia Naves e Rogério "
                "Marcos Garcia Naves; a 3ª com a área de 03,17,55 ha; "
                "matriculada sob o nº 21.524, atribuída à Vivaldo de Souza "
                "Machado; e a 4ª com a área de 56,73,36 ha; matriculada sob o "
                "nº 21.525, atribuída à Vivaldo de Souza Machado; ficando em "
                "consequência encerrada esta matrícula."
            ),
        ]

        resultado = calcular_cadeia_dominial(atos)
        proporcoes = {item['nome']: item['proporcao'] for item in resultado}

        self.assertEqual(proporcoes['Vivaldo de Souza Machado'], '41,67%')
        self.assertEqual(proporcoes['Rosana das Graças Garcia Naves'], '14,58%')
        self.assertEqual(proporcoes['Réginer Aparecida Garcia Naves'], '14,58%')
        self.assertEqual(proporcoes['Rosidelma Garcia Naves'], '14,58%')
        # O centésimo residual é atribuído ao último titular para a soma
        # apresentada fechar exatamente em 100%.
        self.assertEqual(proporcoes['Rogério Marcos Garcia Naves'], '14,59%')

    def test_permuta_com_passou_a_pertencer(self):
        descricao = (
            "PERMUTA. O imóvel constante da presente matrícula passou a "
            "pertencer aos primeiros permutantes José Joaquim Cândido, CPF "
            "076.751.511-00, sendo transmitentes os segundos permutantes."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(resultado[0]["nome"], "José Joaquim Cândido")

    def test_permuta_historica_com_virgula_antes_do_primeiro_permutante(self):
        descricao = (
            "PERMUTA. O imóvel objeto da presente matrícula passou a pertencer "
            "ao primeiro permutante, MUNICÍPIO DE MORRINHOS, pessoa jurídica, "
            "inscrito no CNPJ/MF sob o nº 01.789.551/0001-49, representado pelo "
            "Prefeito Municipal Cleumar Gomes de Freitas; sendo transmitente o "
            "segundo permutante JAIR RODRIGUES DA CUNHA, CPF nº 035.500.281-72."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            [(item["nome"], item["cpf"]) for item in resultado],
            [("MUNICÍPIO DE MORRINHOS", "01.789.551/0001-49")],
        )

    def test_partilha_com_percentual_antes_de_pertencente(self):
        descricao = (
            "INVENTÁRIO/PARTILHA. TRANSMITENTE: Espólio de Wanda Prudente. "
            "ADQUIRENTES: O Meeiro: 1) 50% equivalente a 1/2 do imóvel "
            "pertencente a CLODOALDO PRUDENTE, CPF 004.896.706-87; "
            "Os Herdeiros: 2) 50% equivalente a 1/2 do imóvel pertencente a "
            "ADRIANA RIBEIRO PRUDENTE, CPF 652.195.896-87. "
            "IMÓVEL: 100% do imóvel."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "CLODOALDO PRUDENTE": "50%",
                "ADRIANA RIBEIRO PRUDENTE": "50%",
            },
        )

    def test_partilha_com_meeiro_e_varios_herdeiros(self):
        descricao = (
            "INVENTÁRIO/PARTILHA. ADQUIRENTES: O Meeiro: 1) 50% equivalente "
            "a 1/2 do imóvel pertencente a CLODOALDO PRUDENTE, CPF "
            "004.896.706-87; Os Herdeiros: 2) 5,55% do imóvel pertencente a "
            "ADRIANA RIBEIRO PRUDENTE, CPF 652.195.896-87; 3) 5,55% do imóvel "
            "pertencente a COLETO PRUDENTE, CPF 111.111.111-11; 4) 5,55% do "
            "imóvel pertencente a ELIANA PRUDENTE, CPF 222.222.222-22. "
            "IMÓVEL: 100% do imóvel."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            [item["nome"] for item in resultado],
            [
                "CLODOALDO PRUDENTE",
                "ADRIANA RIBEIRO PRUDENTE",
                "COLETO PRUDENTE",
                "ELIANA PRUDENTE",
            ],
        )
        self.assertEqual(
            [item["proporcao"] for item in resultado],
            ["50%", "5,55%", "5,55%", "5,55%"],
        )

    def test_divisao_prioriza_coube_exclusivamente_sobre_outorgados(self):
        descricao = (
            "DIVISÃO. OUTORGADOS: Ana Silva, CPF 111.111.111-11; Bruno Silva, "
            "CPF 222.222.222-22; Joviano Matias Primo, CPF 333.333.333-33 e "
            "sua mulher Maria José Alves Matias, CPF 444.444.444-44. Coube "
            "exclusivamente aos condôminos Joviano Matias Primo, CPF "
            "333.333.333-33 e sua mulher Maria José Alves Matias, CPF "
            "444.444.444-44, o quinhão constante desta matrícula."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"] for item in resultado},
            {"Joviano Matias Primo", "Maria José Alves Matias"},
        )

    def test_divisao_reaproveita_documentos_dos_condominos_contemplados(self):
        descricao = (
            "DIVISÃO. ADQUIRENTES: 1) Wilian Araújo Teixeira, CPF "
            "394.328.151-53; 2) José Francisco Teixeira, CPF 334.622.911-49; "
            "3) Eusébio Araújo Teixeira, CPF 418.778.531-00; 4) Adelmo Araújo "
            "Teixeira, CPF 486.232.291-34; 5) Leonice Maria de Araújo, CPF "
            "018.888.721-53; coube exclusivamente aos condôminos: 1) Wilian "
            "Araújo Teixeira; 2) José Francisco Teixeira; 3) Eusébio Araújo "
            "Teixeira e Adelmo Araújo Teixeira, já qualificados, a gleba "
            "constante da presente matrícula. DOU FÉ."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"]: item["cpf"] for item in resultado},
            {
                "Wilian Araújo Teixeira": "394.328.151-53",
                "José Francisco Teixeira": "334.622.911-49",
                "Eusébio Araújo Teixeira": "418.778.531-00",
                "Adelmo Araújo Teixeira": "486.232.291-34",
            },
        )

    def test_partilha_em_atos_separados_com_percentuais_do_imovel_substitui_cabecalho(self):
        descricoes = [
            (
                "FORMAL DE PARTILHA extraído do inventário dos bens deixados "
                "por falecimento de EURÍPEDES SEBASTIÃO ANTONINHO. Coube à "
                "viúva meeira IRACI MARQUES ANTONINHO, CPF 942.536.171-15, "
                "parte ideal de 50% sobre o imóvel objeto desta matrícula."
            ),
            (
                "FORMAL DE PARTILHA extraído do inventário dos bens deixados "
                "por falecimento de EURÍPEDES SEBASTIÃO ANTONINHO. Coube ao "
                "herdeiro OVÍDIO MARQUES ANTONINHO, CPF 709.172.721-53, "
                "parte ideal de 50% sobre o imóvel objeto desta matrícula."
            ),
        ]
        texto = (
            "MATRÍCULA 7.580. PROPRIETÁRIOS: Eurípedes Sebastião Antoninho, "
            "CPF 083.935.671-49 e Iraci Marques Antoninho, CPF "
            "942.536.171-15. ORIGEM: registro anterior. "
        )

        resultado = calcular_cadeia_dominial(
            [ato(descricao) for descricao in descricoes],
            texto,
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "IRACI MARQUES ANTONINHO": "50%",
                "OVÍDIO MARQUES ANTONINHO": "50%",
            },
        )

    def test_divisao_interrompe_na_nota_e_separa_esposo_contemplado(self):
        descricao = (
            "DIVISÃO AMIGÁVEL. Celebrada entre os outorgantes. O imóvel "
            "objeto desta matrícula coube exclusivamente aos condôminos: "
            "NERILETE GUIMARÃES LEITE e seu esposo WANDERSON LIMA DE "
            "OLIVEIRA. NOTA* 1)- Ficam isentos do imposto; 2)- Imóvel "
            "cadastrado no INCRA sob o n.º 950.203.116.092-6."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"] for item in resultado},
            {"NERILETE GUIMARÃES LEITE", "WANDERSON LIMA DE OLIVEIRA"},
        )

    def test_espolio_nao_recebe_cpf_do_inventariante(self):
        descricao = (
            "DIVISÃO AMIGÁVEL. Coube exclusivamente ao condômino Espólio de "
            "Maria Rosa de Oliveira e de João Lopes do Nascimento, neste ato "
            "representado por seu inventariante Sebastião Lopes do Nascimento, "
            "inscrito no CPF n.º 333.281.291-20; o imóvel objeto desta matrícula."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["cpf"], "CPF/CNPJ NÃO INFORMADO")

    def test_compra_com_itens_entre_parenteses_e_distribuicao_percentual_final(self):
        compra_integral = (
            "COMPRA E VENDA. O imóvel objeto desta matrícula foi adquirido por: "
            "(1) Luis Antônio Pereira Castilho, CPF 056.882.618-38; "
            "(2) Lucas Castilho Silva, CPF 321.402.448-50; "
            "(3) Paulo Márcio Castilho Silva, CPF 397.827.468-00; por compra "
            "feita aos proprietários anteriores. Este imóvel é adquirido da "
            "seguinte maneira: Luis Antônio Pereira Castilho 50%; Lucas "
            "Castilho Silva 25%; Paulo Márcio Castilho Silva 25%. "
            "O referido é verdade."
        )
        venda_metade = (
            "COMPRA E VENDA. 50% do imóvel objeto desta matrícula foi adquirido "
            "por LUIS ANTÔNIO PEREIRA CASTILHO, CPF 056.882.618-38; por compra "
            "feita a LUCAS CASTILHO SILVA, CPF 321.402.448-50; e PAULO MÁRCIO "
            "CASTILHO SILVA, CPF 397.827.468-00; sem condições."
        )

        resultado = calcular_cadeia_dominial(
            [ato(compra_integral), ato(venda_metade)]
        )

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "LUIS ANTÔNIO PEREIRA CASTILHO",
                    "cpf": "056.882.618-38",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )

    def test_partilha_com_percentual_em_pagamento_de_cessao(self):
        descricoes = [
            (
                "ESCRITURA DE ARROLAMENTO E PARTILHA dos bens deixados por "
                "falecimento de Alfredo Morais Machado. Coube ao herdeiro "
                "Jefferson Alves Machado, CPF 041.093.801-70, em pagamento "
                "de sua herança 50% no valor de R$10.000,00, sobre o imóvel."
            ),
            (
                "ESCRITURA DE ARROLAMENTO E PARTILHA dos bens deixados por "
                "falecimento de Alfredo Morais Machado. Coube à cessionária "
                "Ilda Paulina Machado, CPF 413.939.531-15, em pagamento cessão "
                "em virtude de aquisição dos direitos hereditários, 50% no "
                "valor de R$10.000,00, sobre o imóvel."
            ),
            (
                "COMPRA E VENDA. Parte correspondente a 50% do imóvel foi "
                "adquirida por Ilda Paulina Machado, CPF 413.939.531-15, por "
                "compra feita a Jefferson Alves Machado, CPF 041.093.801-70."
            ),
        ]

        resultado = calcular_cadeia_dominial(
            [ato(descricao) for descricao in descricoes]
        )

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Ilda Paulina Machado",
                    "cpf": "413.939.531-15",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )

    def test_venda_sem_preposicao_antes_do_transmitente_debita_quota(self):
        compra_integral = (
            "COMPRA E VENDA. O imóvel foi adquirido por Marinho Januário de "
            "Souza, CPF 057.730.751-72; e Wilson Januário de Souza, CPF "
            "218.675.421-53; por compra feita aos proprietários anteriores."
        )
        venda_wilson = (
            "COMPRA E VENDA. 50% do imóvel foi adquirido pela Firma Produtos "
            "Globo de Cereais Ltda, CNPJ 02.842.094/0001-71; por compra feita "
            "Wilson Januário de Souza, CPF 218.675.421-53; pelo preço ajustado."
        )

        resultado = calcular_cadeia_dominial(
            [ato(compra_integral), ato(venda_wilson)]
        )

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Marinho Januário de Souza": "50%",
                "Firma Produtos Globo de Cereais Ltda": "50%",
            },
        )

    def test_compra_com_lista_numerada_sem_por_antes_dos_adquirentes(self):
        compra = (
            "COMPRA E VENDA. O imóvel objeto da presente matrícula foi "
            "adquirido 1)- Luis Antônio Pereira Castilho, CPF "
            "056.882.618-38; 2)- Márcio Cunha Silva, CPF 050.526.698-95; "
            "por compra feita a Joaquim Antônio Alves Lelis e Dulcineia "
            "Storto Alves Lelis; pelo preço ajustado."
        )
        venda = (
            "COMPRA E VENDA. 50% do imóvel foi adquirido por Luis Antônio "
            "Pereira Castilho, CPF 056.882.618-38; por compra feita a Márcio "
            "Cunha Silva, CPF 050.526.698-95; sem condições."
        )

        resultado = calcular_cadeia_dominial([ato(compra), ato(venda)])

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Luis Antônio Pereira Castilho",
                    "cpf": "056.882.618-38",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )

    def test_referencia_ao_tabelionato_nao_cria_adquirente(self):
        descricao = (
            "DAÇÃO EM PAGAMENTO. TRANSMITENTE/DADOR: Cerâmica Santa Fé Ltda, "
            "CNPJ 01.459.627/0001-78. ADQUIRENTE/TOMADOR: João Elias Peres "
            "(Espólio), inscrito no CPF 017.292.171-68, falecido conforme "
            "matrícula do Cartório de Registro Civil e Tabelionato de Notas "
            "desta cidade, e era casado com Zarife Francisca Peres, inscrita "
            "no CPF 342.058.701-59. IMÓVEL: O descrito na matrícula."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(len(resultado), 1)
        self.assertTrue(resultado[0]["nome"].startswith("João Elias Peres"))
        self.assertEqual(resultado[0]["cpf"], "017.292.171-68")

    def test_arrematacao_com_coube_ao_arrematante_substitui_dominio(self):
        descricao = (
            "ARREMATAÇÃO. Ação executiva contra Norton Ferreira de Souza e "
            "Ernesto Lopes; coube ao arrematante Ernesto Lopes, brasileiro, "
            "CPF 190.594.428-49; o imóvel constante da presente matrícula, "
            "pelo maior lance oferecido."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Ernesto Lopes",
                    "cpf": "190.594.428-49",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )

    def test_partilha_com_a_proporcao_de_cada_adquirente_totaliza_imovel(self):
        partilha = (
            "INVENTÁRIO/PARTILHA. TRANSMITENTE: Espólio de Maria Luiza Paula, "
            "CPF 391.766.731-20. ADQUIRENTES: 1)- Jerônimo Joaquim de Paula, "
            "CPF 077.348.161-34, a proporção de 50% do imóvel descrito na "
            "matrícula; e 2)- Clebio Ney de Paula, CPF 824.646.851-00, a "
            "proporção de 50% do imóvel descrito na matrícula. IMÓVEL: O "
            "imóvel descrito na matrícula."
        )
        doacao = (
            "DOAÇÃO. DOADOR: Jerônimo Joaquim de Paula, CPF 077.348.161-34. "
            "DONATÁRIO: Clebio Ney de Paula, CPF 824.646.851-00. IMÓVEL: A "
            "proporção de 50% do imóvel descrito na matrícula."
        )

        resultado = calcular_cadeia_dominial([ato(partilha), ato(doacao)])

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Clebio Ney de Paula",
                    "cpf": "824.646.851-00",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )

    def test_usucapiao_promovida_pelo_casal(self):
        descricao = (
            "USUCAPIÃO. A ação de usucapião, promovida por Abadio Pio da "
            "Costa, brasileiro, e, sua mulher Lauriana Maria da Costa, "
            "brasileira, ambos casados, CPF 016.778.371-87, conferindo-lhes "
            "o domínio do imóvel."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"] for item in resultado},
            {"Abadio Pio da Costa", "Lauriana Maria da Costa"},
        )

    def test_empresa_com_cgc_pontuado_nao_herda_cpf_do_representante(self):
        descricao = (
            "DOAÇÃO. O imóvel foi adquirida pela Companhia de Habitação de "
            "Goiás COHAB-GO, inscrita no C.G.C sob n.º 012.742.40/0001-47, "
            "neste ato representada por Cláudio Pereira, CPF 003.958.201-97, "
            "por doação feita pelo Município."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(resultado[0]["nome"], "Companhia de Habitação de Goiás COHAB-GO")
        self.assertEqual(resultado[0]["cpf"], "012.742.40/0001-47")

    def test_venda_individualizada_debita_quota_certa_de_cada_alienante(self):
        descricao = (
            "COMPRA E VENDA. Título lavrado no Livro 247, fls. 124; Manoel "
            "Antônio de Mendonça, CPF 154.412.291-87; adquiriu por compra "
            "feita a: 1) Afonso Gomes Arantes, CPF "
            "093.927.421-34; e 2) Ancelmo Gomes Arantes, CPF 134.355.071-87; "
            "parte correspondente a 75% do imóvel. O imóvel é vendido da "
            "seguinte maneira: 1) Afonso Gomes Arantes vende apenas 25% do "
            "imóvel e, 2) Ancelmo Gomes Arantes vendeu 50% do imóvel. "
            "O referido é verdade."
        )
        texto = (
            "MATRÍCULA 10.724. PROPRIETÁRIOS: 1) Ancelmo Gomes Arantes, CPF "
            "134.355.071-87; 2) Afonso Gomes Arantes, CPF 093.927.421-34. "
            "ORIGEM: registro anterior. R.02-10.724 - " + descricao
        )

        resultado = calcular_cadeia_dominial([ato(descricao)], texto)

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Afonso Gomes Arantes",
                    "cpf": "093.927.421-34",
                    "proporcao": "25%",
                    "proporcao_incerta": False,
                    "proporcao_incerta": False,                },
                {
                    "nome": "Manoel Antônio de Mendonça",
                    "cpf": "154.412.291-87",
                    "proporcao": "75%",
                    "proporcao_incerta": False,
                    "proporcao_incerta": False,                },
            ],
        )

    def test_permuta_com_rotulos_primeira_e_segunda_permutante(self):
        descricao = (
            "PERMUTA. TRANSMITENTE/PRIMEIRA PERMUTANTE: Leidiane Aparecida "
            "Chagas Costa, CPF 001.157.801-73. ADQUIRENTE/SEGUNDA PERMUTANTE: "
            "Leiviane Aparecida Chagas Costa, CPF 008.537.381-81. IMÓVEL: "
            "equivalente a 33,33% do imóvel. DOU FÉ."
        )
        texto = (
            "MATRÍCULA 39.098. PROPRIETÁRIA: Leidiane Aparecida Chagas Costa, "
            "CPF 001.157.801-73. ORIGEM: registro anterior. R.03-39.098 - "
            + descricao
        )

        resultado = calcular_cadeia_dominial([ato(descricao)], texto)

        self.assertEqual(
            [(item["nome"], item["proporcao"]) for item in resultado],
            [
                ("Leidiane Aparecida Chagas Costa", "66,67%"),
                ("Leiviane Aparecida Chagas Costa", "33,33%"),
            ],
        )

    def test_integralizacao_debita_titular_indicado_como_proprietario(self):
        descricao = (
            "INCORPORAÇÃO DE BENS PARA INTEGRALIZAÇÃO DE CAPITAL. Parte de 50% "
            "do imóvel objeto da presente matrícula de propriedade de Clodoaldo "
            "Prudente, avaliado em R$140.182,69, foi incorporado ao patrimônio "
            "da sociedade empresária limitada Clodoaldo Prudente Agropecuária LTDA, inscrita no "
            "CNPJ 56.070.495/0001-80, pelo sócio Clodoaldo Prudente. "
            "O Capital Social total da empresa será de R$283.645,00."
        )
        texto = (
            "MATRÍCULA 26.655. PROPRIETÁRIOS: 1) Clodoaldo Prudente, CPF "
            "111.111.111-11 (50%); 2) Adriana Ribeiro Prudente, CPF "
            "222.222.222-22 (50%). ORIGEM: registro anterior. "
            "R.03-26.655 - " + descricao
        )

        resultado = calcular_cadeia_dominial([ato(descricao)], texto)

        self.assertEqual(
            [(item["nome"], item["proporcao"]) for item in resultado],
            [
                ("Adriana Ribeiro Prudente", "50%"),
                ("Clodoaldo Prudente Agropecuária LTDA", "50%"),
            ],
        )

    def test_retificacao_cpf_atualiza_documento_sem_redistribuir_quinhoes(self):
        retificacao = (
            "RETIFICAÇÃO DE CPF/MF. A co-proprietária Lucíola Rodrigues Jaime "
            "é inscrita no CPF/MF sob o n.º 644.172.128-72 e não como constou; "
            "2.1)- José Batista Jaime é inscrito no CPF/MF sob o n.º "
            "026.175.368-15."
        )
        texto = (
            "MATRÍCULA 1.372. PROPRIETÁRIOS: 1) Lucíola Rodrigues Jaime, CPF "
            "111.111.111-11 (25%); 2) Gil Teodoro Rodrigues, CPF "
            "222.222.222-22 (75%). ORIGEM: registro anterior. "
            "AV.22-1.372 - " + retificacao
        )

        resultado = calcular_cadeia_dominial([ato(retificacao)], texto)

        self.assertEqual(
            {item["nome"]: (item["cpf"], item["proporcao"]) for item in resultado},
            {
                "Lucíola Rodrigues Jaime": ("644.172.128-72", "25%"),
                "Gil Teodoro Rodrigues": ("222.222.222-22", "75%"),
            },
        )

    def test_cancelamento_retorna_ao_status_quo_e_atualiza_denominacao(self):
        atos = [
            ato(
                "CANCELAMENTO DE COMPRA E VENDA. O imóvel retorna ao STATUS QUO "
                "ANTE, ou seja, à propriedade da Companhia de Distritos "
                "Industriais de Goiás - GOIASINDUSTRIAL, inscrita no CNPJ/MF sob "
                "o n.º 01.285.170/0001-22."
            ),
            ato(
                "MUDANÇA DE DENOMINAÇÃO SOCIAL. A proprietária Companhia de "
                "Distritos Industriais de Goiás - GOIASINDUSTRIAL, CNPJ "
                "01.285.170/0001-22, passou a denominar-se Companhia de "
                "Desenvolvimento Econômico de Goiás - CODEGO, empresa pública."
            ),
        ]

        resultado = calcular_cadeia_dominial(atos)

        self.assertEqual(
            resultado,
            [
                {
                    "nome": "Companhia de Desenvolvimento Econômico de Goiás - CODEGO",
                    "cpf": "01.285.170/0001-22",
                    "proporcao": "100%",
                    "proporcao_incerta": False,
                }
            ],
        )


    def test_partilha_da_viuva_meeira_nao_duplica_quinhao_existente(self):
        texto = (
            "MATRÍCULA 81. IMÓVEL: lote. PROPRIETÁRIOS: Luzia Alves da "
            "Costa Barros, CPF 111.111.111-11, na proporção de 16,67%; Maria Alves da Costa "
            "Santos, na proporção de 83,33%. ORIGEM: registro anterior."
        )
        descricao = (
            "FORMAL DE PARTILHA dos bens deixados por falecimento de Joedes "
            "Ferreira de Barros; coube à viúva meeira Luzia Alves da Costa "
            "Barros, CPF 222.222.222-22, em pagamento de sua meação, parte correspondente a "
            "16,67% do imóvel."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)], texto)

        self.assertEqual(
            {item['nome']: item['proporcao'] for item in resultado},
            {
                'Luzia Alves da Costa Barros': '16,67%',
                'Maria Alves da Costa Santos': '83,33%',
            },
        )

    def test_espolio_substitui_quinhao_de_herdeiro_que_ja_constava(self):
        texto = (
            "MATRÍCULA 128. IMÓVEL: lote. PROPRIETÁRIOS: Ellen Carneiro Vale, "
            "na proporção de 50%; Tania Maria Carneiro do Vale, na proporção "
            "de 50%. ORIGEM: registro anterior."
        )
        descricao = (
            "INVENTÁRIO/PARTILHA. TRANSMITENTE: O Espólio de Cristovão do "
            "Vale. ADQUIRENTES: 1) Tania Maria Carneiro do Vale, parte "
            "correspondente a 7,14% do imóvel; 2) Lucia Carneiro Vale, parte "
            "correspondente a 42,86% do imóvel. IMÓVEL: A proporção de 50% "
            "do imóvel descrito na matrícula."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)], texto)

        self.assertEqual(
            {item['nome']: item['proporcao'] for item in resultado},
            {
                'Ellen Carneiro Vale': '50%',
                'Tania Maria Carneiro do Vale': '7,14%',
                'Lucia Carneiro Vale': '42,86%',
            },
        )


if __name__ == "__main__":
    unittest.main()
