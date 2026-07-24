import unittest

from backend.app.servicos.analise_matricula import analisar_matricula


def valores_por_rotulo(itens, rotulo):
    return [item["valor"] for item in itens if item["rotulo"] == rotulo]


class TesteDadosImovel(unittest.TestCase):
    def test_area_urbana_com_ponto_de_milhar(self):
        texto = (
            "MATRÍCULA 39.630. IMÓVEL: Lote n.º 26, Quadra 36, com área de "
            "1.152m², situado na Rua Rio Grande do Sul, Centro. "
            "PROPRIETÁRIA: Pessoa Teste."
        )

        resultado = analisar_matricula(texto, numero_matricula="39630")["imovel"]

        self.assertIn(
            {"rotulo": "Área", "valor": "1.152 m²", "origem": "Cabeçalho"},
            resultado["areas"],
        )

    def test_area_rural_com_e_entre_hectares_e_ares(self):
        texto = (
            "MATRÍCULA 17.971. IMÓVEL: Fazenda Formiga, com a área de "
            "49 (quarenta e nove) hectares e 84 (oitenta e quatro) ares e "
            "09 (zero nove centiares). PROPRIETÁRIO: Pessoa Teste."
        )

        resultado = analisar_matricula(texto, numero_matricula="17971")["imovel"]

        self.assertIn(
            {"rotulo": "Área", "valor": "49,8409 ha", "origem": "Cabeçalho"},
            resultado["areas"],
        )

    def test_encerramento_ficando_em_consequencia(self):
        texto = (
            "MATRÍCULA 21. IMÓVEL: Fazenda Areias. PROPRIETÁRIO: Pessoa Teste.\n"
            "AV.01-21. O imóvel foi unificado a outros, ficando em consequência "
            "encerrada esta matrícula. DOU FÉ."
        )

        resultado = analisar_matricula(texto, numero_matricula="21")["imovel"]

        self.assertEqual("ENCERRADA", resultado["situacao"]["status"])

    def test_cci_para_antes_do_valor_da_obra(self):
        texto = (
            "MATRÍCULA 27.822. IMÓVEL: Lote 03, Quadra D, com área de 176,10m². "
            "PROPRIETÁRIO: Pessoa Teste.\n"
            "AV.03-27.822 - EDIFICAÇÃO. Designação cadastral do imóvel: "
            "CCI n.º 132.622. Valor da obra: R$87.985,78. DOU FÉ."
        )

        resultado = analisar_matricula(texto, numero_matricula="27822")["imovel"]

        self.assertIn(
            {
                "rotulo": "Cadastro municipal",
                "valor": "CCI 132.622",
                "origem": "AV.03",
            },
            resultado["cadastros"],
        )

    def test_cci_com_virgula_de_milhar_vira_um_codigo(self):
        texto = (
            "MATRÍCULA 18.450. IMÓVEL: Lote 13, Quadra S, com área de 250m². "
            "PROPRIETÁRIO: Pessoa Teste.\n"
            "AV.04-18.450 - DESIGNAÇÃO CADASTRAL DO IMÓVEL. O imóvel possui "
            "o seguinte código cadastral: CCI n.º 123,152. DOU FÉ."
        )

        resultado = analisar_matricula(texto, numero_matricula="18450")["imovel"]

        self.assertIn(
            {
                "rotulo": "Cadastro municipal",
                "valor": "CCI 123.152",
                "origem": "AV.04",
            },
            resultado["cadastros"],
        )

    def test_area_construida_com_total_de_apos_rotulo(self):
        texto = (
            "IMÓVEL: Lote n.º 1, com área de 200,00m².\n"
            "AV.01-1 - Data: 01.01.2025. EDIFICAÇÃO. Foi edificada uma construção de uso misto, "
            "com área construída total de 147,08m². DOU FÉ."
        )

        resultado = analisar_matricula(texto)["imovel"]

        self.assertIn(
            {"rotulo": "Área Construída", "valor": "147,08 m²", "origem": "AV.01"},
            resultado["areas"],
        )

    def test_car_corrige_zero_usado_no_lugar_da_letra_o_na_uf(self):
        texto = (
            "IMÓVEL: Fazenda Teste, com área de 10,00 ha.\n"
            "AV.01-1 - Data: 01.01.2025. CADASTRO AMBIENTAL RURAL. O imóvel foi inscrito no CAR sob o "
            "n.º de registro G0-5213806-E772.4DAD.A6BC.46EA.A559.FF65.4370.A9BF, "
            "cadastrado em 29.11.2016. DOU FÉ."
        )

        resultado = analisar_matricula(texto)["imovel"]

        self.assertIn(
            {
                "rotulo": "CAR",
                "valor": "GO-5213806-E772.4DAD.A6BC.46EA.A559.FF65.4370.A9BF",
                "origem": "AV.01",
            },
            resultado["cadastros"],
        )

    def test_area_total_do_terreno_urbano(self):
        texto = """
        MATRÍCULA 703. IMÓVEL: Rua Exemplo, n.º 10, com área total de 312,00m²,
        contendo uma casa com área total construída de 109,85m².
        PROPRIETÁRIO: Pessoa Exemplo. ORIGEM: Matrícula anterior.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área"), ["312 m²"])

    def test_designacao_cadastral_singular_inclui_cci_da_averbacao(self):
        texto = """
        IMÓVEL: Lote n.º 27-B, da Quadra 66, com área de 125,10m², situado na
        Rua Novara, Jardim Romano, nesta cidade. PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-39.000 - CÓDIGO DE ENDEREÇAMENTO POSTAL. O imóvel possui o
        CEP n.º 75.656-118. DOU FÉ.
        AV.02-39.000 - DESIGNAÇÃO CADASTRAL DO IMÓVEL. O imóvel objeto da
        presente matrícula possui o seguinte código cadastral na Prefeitura
        Municipal: CCI n.º 139.796xxx.xxxxxx.xxx. DOU FÉ.
        AV.03-39.000 - EDIFICAÇÃO. Foi edificada uma casa residencial com
        82,37m² de área construída. DOU FÉ.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(
            valores_por_rotulo(resultado["cadastros"], "Cadastro municipal"),
            ["CCI 139.796"],
        )
        self.assertEqual(
            [item["origem"] for item in resultado["cadastros"] if item["rotulo"] == "Cadastro municipal"],
            ["AV.02"],
        )
        self.assertEqual(valores_por_rotulo(resultado["cadastros"], "CEP"), ["75.656-118"])
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área Construída"), ["82,37 m²"])

    def test_matricula_aberta_sem_numero_explicito_usa_primeiro_ato_e_dados_urbanos_atuais(self):
        texto = """
        IMÓVEL: Uma casa de residência situada na Rua Paraíba, n.º 128, nesta cidade,
        com terreno de frente para a rua e fundos com um córrego; cadastrado na Prefeitura
        sob o n.º 1/9-C. ORIGEM: R-05 da Matrícula 7.898. PROPRIETÁRIOS: Proprietários diversos,
        alguns residentes em fazenda neste Município.
        R-01-29.774 - INVENTÁRIO/PARTILHA. IMÓVEL: 2,53% do imóvel descrito na matrícula.
        AV.04-29.774 - ATUALIZAÇÃO DE DESIGNAÇÃO CADASTRAL DO IMÓVEL. O imóvel atualmente
        possui os seguintes códigos cadastrais na Prefeitura Municipal: CCI n.os 9.168,
        9.174 e 129.287. DOU FÉ.
        AV.05-29.774 - CARACTERIZAÇÃO DO IMÓVEL. O imóvel assim se caracteriza: Lote n.º 09,
        da Quadra 01, situado na Rua Paraíba, n.º 128, Centro, com área de 10.142,00m²,
        sendo: frente com a citada rua; fundos com o Córrego Maria Lucinda; lateral direita
        com o lote n.º 01 da quadra 02; e lateral esquerda com o lote 08 da quadra 01,
        o lote 07 da quadra 01 e o lote 06 da quadra 01.
        """

        resultado = analisar_matricula(texto)["imovel"]

        identificacao = {item["rotulo"]: item["valor"] for item in resultado["identificacao"]}
        self.assertEqual(identificacao["Matrícula"], "29.774")
        self.assertEqual(identificacao["Lote"], "09")
        self.assertEqual(identificacao["Quadra"], "01")
        self.assertEqual(resultado["tipo"], "URBANO")
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área"), ["10.142 m²"])
        self.assertEqual(
            [(item["rotulo"], item["valor"]) for item in resultado["confrontacoes"]],
            [
                ("Frente", "Rua Paraíba"),
                ("Lado Direito", "Lote 01 da Quadra 02"),
                ("Lado Esquerdo", "Lotes 08, 07 e 06 da Quadra 01"),
                ("Fundos", "Córrego Maria Lucinda"),
            ],
        )
        self.assertEqual(
            [(item["valor"], item["origem"]) for item in resultado["cadastros"]],
            [("CCI 9.168, 9.174 e 129.287", "AV.04")],
        )

    def test_caracterizacao_posterior_substitui_dados_fisicos_e_preserva_numero(self):
        texto = """
        MATRÍCULA 10.597. IMÓVEL: Rua Dr. Pedro Nunes, 1266, nesta cidade,
        constituído de um prédio residencial e terreno com a área de 280,00m²;
        lado esquerdo confrontando com o lote 17 e fundos com o lote 19;
        desmembrado do lote 34 da quadra 08. PROPRIETÁRIA: Proprietária Exemplo.
        AV.02-10.597 - RECONSTRUÇÃO DE PRÉDIO. Prédio com área construída de 47,95m²,
        acréscimo com área construída de 59,69m², passando a ter a área total de 107,64m².
        AV.13-10.597 - CARACTERIZAÇÃO DO IMÓVEL. O imóvel assim se caracteriza:
        Lote n.º 08, Quadra 102, constituído de um prédio residencial com a área construída
        de 107,64m², situado na Rua Dr. Pedro Nunes, Centro, nesta cidade, com área de
        280,00m², dividindo na frente com a citada rua; fundos com o lote n.º 06;
        lateral direita com o lote n.º 09; e lateral esquerda com os lotes n.os 07 e 07-A.
        """

        resultado = analisar_matricula(texto)["imovel"]

        identificacao = {item["rotulo"]: item["valor"] for item in resultado["identificacao"]}
        self.assertEqual(identificacao["Lote"], "08")
        self.assertEqual(identificacao["Quadra"], "102")
        self.assertEqual(identificacao["Rua"], "Rua Dr. Pedro Nunes")
        self.assertEqual(identificacao["Número"], "1266")
        self.assertEqual(identificacao["Setor"], "Centro")
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área"), ["280 m²"])
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área Construída"), ["107,64 m²"])
        self.assertEqual(
            [(item["rotulo"], item["valor"], item["origem"]) for item in resultado["confrontacoes"]],
            [
                ("Frente", "Rua Dr. Pedro Nunes", "AV.13"),
                ("Lado Direito", "Lote 09", "AV.13"),
                ("Lado Esquerdo", "Lotes 07 e 07-A", "AV.13"),
                ("Fundos", "Lote 06", "AV.13"),
            ],
        )

    def test_endereco_preserva_rua_e_setor_composto_do_cabecalho(self):
        texto = """
        IMÓVEL: Lote n.º 04, da Quadra 58, com área de 513,37m², situado na Rua 9,
        Vila Cordeiro, Setor Oeste, nesta cidade, com as seguintes medidas e confrontações:
        dividindo na frente com a citada rua; nos fundos com o lote n.º 17; na lateral
        direita com o lote n.º 05; e na lateral esquerda com o lote n.º 03.
        PROPRIETÁRIA: Proprietária Exemplo.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(valores_por_rotulo(resultado["imovel"]["identificacao"], "Rua"), ["Rua 9"])
        self.assertEqual(
            valores_por_rotulo(resultado["imovel"]["identificacao"], "Setor"),
            ["Vila Cordeiro, Setor Oeste"],
        )

    def test_endereco_remove_prefixo_do_loteamento_antes_do_setor(self):
        texto = """
        MATRÍCULA 15.000. IMÓVEL: Lote n.º 10, da Quadra 20, com área de 300,00m²,
        situado na Rua 8, do loteamento Setor Aeroporto II, nesta cidade.
        PROPRIETÁRIO: Proprietário Exemplo, CPF 111.111.111-11.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(valores_por_rotulo(resultado["identificacao"], "Rua"), ["Rua 8"])
        self.assertEqual(
            valores_por_rotulo(resultado["identificacao"], "Setor"),
            ["Setor Aeroporto II"],
        )

    def test_confrontacoes_exibem_somente_os_lotes(self):
        texto = """
        MATRÍCULA 29.460. IMÓVEL: Lote n.º 08, da quadra 12, com a área de 360,00m²,
        confrontando pela frente com o lote nº 21; pelo lado direito com o lote 09-A;
        pelo lado esquerdo com o lote de terras n.º 07 e pelos fundos com os lotes 15 e 16.
        PROPRIETÁRIO: Proprietário Exemplo, CPF 111.111.111-11.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(
            resultado["imovel"]["confrontacoes"],
            [
                {"rotulo": "Frente", "valor": "Lote 21", "origem": "Cabeçalho"},
                {"rotulo": "Lado Direito", "valor": "Lote 09-A", "origem": "Cabeçalho"},
                {"rotulo": "Lado Esquerdo", "valor": "Lote 07", "origem": "Cabeçalho"},
                {"rotulo": "Fundos", "valor": "Lotes 15 e 16", "origem": "Cabeçalho"},
            ],
        )

    def test_matricula_1560_reconhece_hipoteca_encerramento_e_representante(self):
        texto = """
        MATRÍCULA 1.560. IMÓVEL: Lote n.º 4, da quadra 87, Avenida 101,
        com a área de 633,50m². PROPRIETÁRIO: Município Exemplo, CNPJ 01.111.111/0001-11.
        R.01-1.560 - DOAÇÃO. O imóvel foi adquirido pela Companhia de Habitação Exemplo,
        CNPJ 01.274.240/0001-47, neste ato representada por seu Diretor Presidente,
        CPF 002.741.941-04; por doação que lhe fez o Município Exemplo.
        R.02-1.560 - EMPRÉSTIMO. O imóvel foi dado em garantias hipotecária e suplementar,
        em 1ª e especial hipoteca transferível a terceiros, ao Banco Credor.
        AV.03-1.560 - UNIFICAÇÃO E ABERTURA DE NOVA MATRÍCULA. O imóvel foi matriculado
        sob o n.º 3.432, com o que fica encerrada a presente.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(resultado["imovel"]["situacao"]["status"], "ENCERRADA")
        self.assertEqual(resultado["imovel"]["situacao"]["matricula_sucessora"], "3.432")
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["areas"], "Área"), ["633,5 m²"])
        self.assertEqual(
            resultado["proprietarios_atuais"],
            [{"nome": "Companhia de Habitação Exemplo", "cpf": "01.274.240/0001-47", "proporcao": "100%"}],
        )

    def test_desmembramento_integral_em_duas_glebas_encerra_matricula(self):
        texto = """
        MATRÍCULA 1. IMÓVEL: Fazenda Exemplo, com área de 273,3400ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.08-1 - DESMEMBRAMENTO E MATRÍCULA. Averba-se o desmembramento do imóvel
        matriculado em duas glebas de terras, contendo a primeira a área de 176,5400ha,
        que foi matriculada sob o n.º 12.015, e a segunda a área de 96,8000ha,
        matriculada sob o n.º 12.016.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(
            resultado["situacao"],
            {
                "status": "ENCERRADA",
                "origem": "AV.08",
                "matriculas_sucessoras": ["12.015", "12.016"],
            },
        )

    def test_desmembramento_parcial_com_remanescente_nao_encerra_matricula(self):
        texto = """
        MATRÍCULA 500. IMÓVEL: Fazenda Exemplo, com área de 100ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-500 - DESMEMBRAMENTO. Foi destacada uma área de 20ha, matriculada sob
        o n.º 12.500, permanecendo a área remanescente nesta matrícula.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(resultado["situacao"]["status"], "ATIVA")

    def test_redacao_encerrada_a_presente_matricula_reconhece_encerramento(self):
        texto = """
        MATRÍCULA 700. IMÓVEL: Lote n.º 01, Quadra 02, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo. ORIGEM: Matrícula anterior.
        AV.02-700 - ABERTURA DE NOVA MATRÍCULA. O imóvel foi matriculado sob o
        n.º 12.700, sendo encerrada a presente matrícula.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(resultado["situacao"]["status"], "ENCERRADA")
        self.assertEqual(resultado["situacao"]["origem"], "AV.02")
        self.assertEqual(resultado["situacao"]["matricula_sucessora"], "12.700")

    def test_redacao_encerra_se_a_presente_matricula_reconhece_encerramento(self):
        texto = """
        MATRÍCULA 701. IMÓVEL: Lote n.º 02, Quadra 02, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo. ORIGEM: Matrícula anterior.
        AV.03-701 - REMEMBRAMENTO. O imóvel foi matriculado sob o n.º 12.701.
        Encerra-se a presente matrícula.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(resultado["situacao"]["status"], "ENCERRADA")
        self.assertEqual(resultado["situacao"]["matricula_sucessora"], "12.701")

    def test_formatos_historicos_de_area_cci_ccir_e_cep_de_parte(self):
        texto = """
        MATRÍCULA 702. IMÓVEL: Fazenda Exemplo, com a área de 273,34,00 hectares.
        PROPRIETÁRIO: Pessoa Exemplo. ORIGEM: Matrícula anterior.
        AV.01-702 - EDIFICAÇÃO. Casa com a área construída, de 40,00m².
        R.02-702 - COMPRA E VENDA. *Designação cadastral do imóvel:
        CCI n.º 100.001 e 100.002. DOU FÉ.
        AV.03-702 - ATUALIZAÇÃO DO CCIR. Código do Imóvel Rural 936.120.031.330-0,
        área total de 273,3400ha. DOU FÉ.
        AV.04-702 - QUALIFICAÇÃO DA PARTE. A sociedade possui sede na Rua Exemplo,
        CEP n.º 75.650-000. DOU FÉ.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área"), ["273,34 ha"])
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área Construída"), ["40 m²"])
        self.assertEqual(valores_por_rotulo(resultado["cadastros"], "Cadastro municipal"), ["CCI 100.001 e 100.002"])
        self.assertEqual(valores_por_rotulo(resultado["cadastros"], "CCIR / código rural"), ["936.120.031.330-0"])
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área no CCIR"), ["273,34 ha"])
        self.assertEqual(valores_por_rotulo(resultado["cadastros"], "CEP"), [])

    def test_matricula_8148_extrai_lote_area_e_edificacao(self):
        texto = """
        MATRÍCULA 8.148. IMÓVEL: Rua CR-6, Setor Cristo Redentor, lote n.º 03,
        da quadra 58, com a área de 360,00m². PROPRIETÁRIO: Imobiliária Exemplo Ltda.
        AV.02-8.148 - EDIFICAÇÃO DE PRÉDIO. Edificação residencial com a área construída
        de 41,48m².
        R.06-8.148 - COMPRA E VENDA. O imóvel foi adquirido por Irani Francisca de Rezende,
        CPF 004.338.341-61; por compra feita à proprietária anterior.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(resultado["resultado"], "NEGATIVA PARA ÔNUS")
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["identificacao"], "Lote"), ["03"])
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["identificacao"], "Quadra"), ["58"])
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["areas"], "Área Construída"), ["41,48 m²"])
        self.assertFalse(valores_por_rotulo(resultado["imovel"]["identificacao"], "Descrição registral"))
        self.assertEqual(
            [item["rotulo"] for item in resultado["imovel"]["areas"][:2]],
            ["Área", "Área Construída"],
        )

    def test_matricula_10148_corrige_partilha_e_preserva_areas_por_fonte(self):
        texto = """
        MATRÍCULA 10.148. IMÓVEL: Fazenda Santa Rosa, lugar denominado Retiro da Moeda,
        neste Município, com a área de 92 hectares, 98 ares e 85 centiares.
        PROPRIETÁRIO: Proprietário Inicial, CPF 111.111.111-11.
        R.06-10.148 - COMPRA E VENDA. O imóvel foi adquirido por Gislaine Ribeiro Ázara
        de Camargos, CPF 129.901.831-91; por compra feita ao proprietário anterior.
        AV.11-10.148 - INSCRIÇÃO NO CAR. Registro GO-5213806-963034EDDD0148FFAC5A4BD078B5A46E,
        área total(ha): 369,1061. Foi detectada uma diferença entre a área declarada conforme
        documentação [395,4885 hectares] e a representação gráfica [369,1061 hectares].
        AV.14-10.148 - ATUALIZAÇÃO DO CCIR. código do imóvel rural: 936.120.031.330-0;
        área total: 92,9000ha.
        R.16-10.148 - INVENTÁRIO/PARTILHA. TRANSMITENTE: O Espólio de Baltazar Camargos.
        ADQUIRENTE: Gislaine Ribeiro Ázara de Camargos, CPF 129.901.831-91.
        IMÓVEL: A proporção de 50% do imóvel. ORIGEM: O R.06 desta matrícula.
        R.17-10.148 - INVENTÁRIO/PARTILHA. TRANSMITENTE: O Espólio de Baltazar Camargos.
        ADQUIRENTE: Angelica Ribeiro Camargos, CPF 969.883.981-04.
        IMÓVEL: A proporção de 50% do imóvel. ORIGEM: O R.06 desta matrícula.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado["proprietarios_atuais"]},
            {"Gislaine Ribeiro Ázara de Camargos": "50%", "Angelica Ribeiro Camargos": "50%"},
        )
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["areas"], "Área"), ["92,9885 ha"])
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["areas"], "Área no CCIR"), ["92,9 ha"])
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["areas"], "Área declarada no CAR"), ["369,1061 ha"])
        self.assertEqual(len(resultado["imovel"]["divergencias"]), 1)

    def test_matricula_10983_extrai_reserva_car_ccir_e_hipoteca_ativa(self):
        texto = """
        MATRÍCULA 10.983. IMÓVEL: Fazendas Três Barras e Vinagre e Santa Rosa,
        com a área de 71 hectares, 68 ares e 48 centiares. Cadastrado no INCRA,
        sob o n.º 936.120.000.914-8. PROPRIETÁRIO: Vanderlei Alves de Mendonça,
        CPF 348.973.641-91.
        AV.05-10.983 - RESERVA LEGAL. Fica preservada a área de 14,3370ha.
        AV.07-10.983 - INSCRIÇÃO NO CAR. registro GO-5213806-8816CCFF2848491099CCA2232FCF3409,
        área total(ha): 69,6469.
        AV.10-10.983 - ATUALIZAÇÃO DO CCIR. código do imóvel rural: 936.120.027.650-2;
        área total: 71,6848ha.
        R.12-10.983 - HIPOTECA. OBJETO DA GARANTIA: Em hipoteca cedular de primeiro grau,
        o imóvel objeto da presente matrícula.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["restricoes"], "Reserva legal"), ["14,337 ha"])
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["cadastros"], "CCIR / código rural"), ["936.120.027.650-2"])
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["areas"], "Área declarada no CAR"), ["69,6469 ha"])

    def test_matricula_29347_reconhece_donataria_e_clausula_restritiva(self):
        texto = """
        MATRÍCULA 29.347. IMÓVEL: Lote n.º 06, Quadra 70-B, situado na Rua 18-B,
        Vila Mutirão, com área de 482,54m². PROPRIETÁRIO: Município Exemplo,
        CNPJ 01.789.551/0001-49.
        R.01-29.347 - DOAÇÃO. DOADOR: Município Exemplo. INTERVENIENTE: Secretaria Municipal.
        DONATÁRIA: Maria Lucia Fernandes da Silva, CPF 333.288.701-72.
        OBJETO: 100% do imóvel. FORMA DO TÍTULO: Instrumento Particular de Doação.
        AV.02-29.347 - CLÁUSULA RESTRITIVA. A donatária não poderá alienar o imóvel
        pelo período de 05 (cinco) anos.
        """

        resultado = analisar_matricula(texto)

        self.assertEqual(resultado["resultado"], "NEGATIVA, PORÉM COM PUBLICIDADE")
        self.assertEqual(
            resultado["proprietarios_atuais"],
            [{"nome": "Maria Lucia Fernandes da Silva", "cpf": "333.288.701-72", "proporcao": "100%"}],
        )
        self.assertEqual(valores_por_rotulo(resultado["imovel"]["restricoes"], "Cláusula restritiva"), ["Prazo declarado de 05 anos"])

    def test_cabecalho_antigo_sem_rotulo_imovel_extrai_lote_e_quadra(self):
        texto = """
        MATRÍCULA - 186. Rua 1-A, da Quadra 5, do Setor Aeroporto, nesta cidade,
        constituído do Lote nº 04, com área de 559,00m².
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(valores_por_rotulo(resultado["identificacao"], "Lote"), ["04"])
        self.assertEqual(valores_por_rotulo(resultado["identificacao"], "Quadra"), ["5"])
        self.assertEqual(valores_por_rotulo(resultado["identificacao"], "Rua"), ["Rua 1-A"])
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área"), ["559 m²"])

    def test_endereco_embutido_na_descricao_historica(self):
        casos = (
            ("J. América. Avenida B. O lote de terras n.º 4", "Avenida B"),
            ("Cordeiro, margem esquerda da Rodovia BR-153, neste Município", "Rodovia BR-153"),
            ("Trevo de confluência da Avenida José do Nascimento, lado descendente", "Avenida José do Nascimento"),
        )
        for descricao, esperado in casos:
            with self.subTest(descricao=descricao):
                texto = f"MATRÍCULA 910. IMÓVEL: {descricao}. PROPRIETÁRIO: Pessoa Exemplo."
                identificacao = analisar_matricula(texto)["imovel"]["identificacao"]
                self.assertEqual(valores_por_rotulo(identificacao, "Rua"), [esperado])

    def test_quadra_generica_sem_numero_nao_gera_valor_de(self):
        texto = """
        MATRÍCULA 911. IMÓVEL: Ruas 1-A, 22 e 203-A, constituído de uma quadra
        de terreno com área de 20.000m². PROPRIETÁRIO: Pessoa Exemplo.
        """
        identificacao = analisar_matricula(texto)["imovel"]["identificacao"]
        self.assertEqual(valores_por_rotulo(identificacao, "Rua"), ["Ruas 1-A"])
        self.assertEqual(valores_por_rotulo(identificacao, "Quadra"), [])

    def test_area_rural_em_metros_quadrados_com_separadores_de_milhar(self):
        texto = """
        MATRÍCULA 127. IMÓVEL: Fazenda Santa Rosa, um quinhão de terras,
        com a área de 1.477.100m². PROPRIETÁRIO: Pessoa Exemplo.
        """

        resultado = analisar_matricula(texto)["imovel"]

        self.assertEqual(resultado["tipo"], "RURAL")
        self.assertEqual(valores_por_rotulo(resultado["areas"], "Área"), ["1.477.100 m²"])

    def test_desmembramento_historico_com_lista_plural_de_sucessoras(self):
        texto = """
        MATRÍCULA 229. IMÓVEL: Fazenda Exemplo, com área de 207,4439ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.08-229 - DESMEMBRAMENTO. Desmembramento do imóvel matriculado em três
        glebas de terras, matriculados sob os n.ºs 13.422; 13.423 e 13.424,
        fls. 211, 212 e 213 do Lº 2-BD, deste Registro.
        """

        situacao = analisar_matricula(texto)["imovel"]["situacao"]

        self.assertEqual(situacao["status"], "ENCERRADA")
        self.assertEqual(situacao["matriculas_sucessoras"], ["13.422", "13.423", "13.424"])

    def test_desmembramento_historico_com_n_singular_antes_da_lista(self):
        texto = """
        MATRÍCULA 13.161. IMÓVEL: Fazenda Exemplo, com área de 227,4800ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.04-13.161 - DESMEMBRAMENTO E MATRÍCULA. Averba-se o desmembramento do
        imóvel matriculado em duas glebas de terras, com as áreas de 145,20,00ha e
        82,28,00ha, que foram matriculadas sob n.º 13.234 e 13.235, fls. 276 e 277
        deste livro.
        """

        situacao = analisar_matricula(texto)["imovel"]["situacao"]

        self.assertEqual(situacao["status"], "ENCERRADA")
        self.assertEqual(situacao["matriculas_sucessoras"], ["13.234", "13.235"])

    def test_formatos_historicos_de_cci_car_e_cep_mascarado(self):
        texto = """
        MATRÍCULA 800. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-800 - CADASTRO MUNICIPAL. Cadastro Municipal nº CCI-56.
        AV.02-800 - INSCRIÇÃO NO CAR. Imóvel inscrito no Cadastro Ambiental Rural -
        CAR sob o nº de registro: GO- 5209101-B139.4AB6.FBD3.4033.
        AV.03-800 - CÓDIGO DE ENDEREÇAMENTO POSTAL. O imóvel possui o seguinte
        CEP nº XX.XXX-XXXXX.XXX-XXX75656-190.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "Cadastro municipal"), ["CCI 56"])
        self.assertEqual(valores_por_rotulo(cadastros, "CAR"), ["GO-5209101-B139.4AB6.FBD3.4033"])
        self.assertEqual(valores_por_rotulo(cadastros, "CEP"), ["75.656-190"])

    def test_cci_em_nota_com_numero_colado_ao_simbolo_ordinal(self):
        texto = """
        MATRÍCULA 25.914. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        R.01-25.914 - COMPRA E VENDA. *NOTA: Constou na escritura a designação
        cadastral do imóvel: CCI n.º130423. DOU FÉ.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "Cadastro municipal"), ["CCI 130423"])

    def test_cci_mascarado_e_apresentado_sem_perder_a_mascara(self):
        texto = """
        MATRÍCULA 29.856. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.05-29.856 - DESIGNACÃO CADASTRAL DO IMÓVEL. O imóvel possui o seguinte
        código cadastral: CCI n.º1908xxx.xxxxxx.xxx. DOU FÉ.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(
            valores_por_rotulo(cadastros, "Cadastro municipal"),
            ["CCI 1908xxx.xxxxxx.xxx"],
        )

    def test_car_com_espacos_e_blocos_separados_por_ponto(self):
        texto = """
        MATRÍCULA 21.062. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.05-21.062 - INSCRIÇÃO NO CAR. Cadastro Ambiental Rural sob o código
        GO - 5213806 - 8D89. 1B2E. C939. 49FE. B818. F888. 56A5. 485A. DOU FÉ.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(
            valores_por_rotulo(cadastros, "CAR"),
            ["GO-5213806-8D89.1B2E.C939.49FE.B818.F888.56A5.485A"],
        )

    def test_car_continuo_apos_rotulo_cadastro_ambiental_rural(self):
        texto = """
        MATRÍCULA 30.425. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-30.425 - INSCRIÇÃO NO CAR. Cadastro Ambiental Rural n.º
        GO-5213806-6F01D8F1B8594924AB6D65E0663CE9CF originalmente averbado na origem.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(
            valores_por_rotulo(cadastros, "CAR"),
            ["GO-5213806-6F01D8F1B8594924AB6D65E0663CE9CF"],
        )

    def test_car_historico_com_sufixo_de_31_caracteres(self):
        texto = """
        MATRÍCULA 33.411. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-33.411 - TRASLADO/INSCRIÇÃO NO CAR. Cadastro Ambiental Rural - CAR
        GO-5213806-86F2514FC0634A19BF1BD89F2A8CECE, datado de 13.06.2014.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(
            valores_por_rotulo(cadastros, "CAR"),
            ["GO-5213806-86F2514FC0634A19BF1BD89F2A8CECE"],
        )

    def test_cep_com_ponto_no_lugar_do_hifen(self):
        texto = """
        MATRÍCULA 15.849. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-15.849 - CÓDIGO DE ENDEREÇAMENTO POSTAL. O imóvel possui o seguinte
        CEP n.º 75.656.098. DOU FÉ.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "CEP"), ["75.656-098"])

    def test_cep_reconstituido_de_mascara_intercalada(self):
        texto = """
        MATRÍCULA 20.449. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-20.449 - CÓDIGO DE ENDEREÇAMENTO POSTAL. O imóvel possui o seguinte
        CEP n.º 75.654xx.xxx-xxxxx.xxx-xxx-210. DOU FÉ.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "CEP"), ["75.654-210"])

    def test_usa_ultima_ocorrencia_de_cep_no_ato(self):
        texto = """
        MATRÍCULA 34.634. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-34.634 - CÓDIGO DE ENDEREÇAMENTO POSTAL. Consulta de CEP emitida
        pelo site dos Correios, nos termos do Provimento n.º 149/2023, para constar
        que o imóvel possui CEP n.º 75650-348. DOU FÉ.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "CEP"), ["75.650-348"])

    def test_area_construida_antes_do_rotulo_com_virgula(self):
        texto = """
        MATRÍCULA 13.017. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-13.017 - EDIFICAÇÃO. Casa residencial com 82,37m², de área construída.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["82,37 m²"])

    def test_area_construida_com_dois_pontos_apos_de(self):
        texto = """
        MATRÍCULA 15.385. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-15.385 - EDIFICAÇÃO. Casa com área construída de: 46,50m².
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["46,5 m²"])

    def test_area_construida_sem_m_antes_do_simbolo_quadrado(self):
        texto = """
        MATRÍCULA 34.428. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-34.428 - EDIFICAÇÃO. Casa residencial com 110,20² de área construída.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["110,2 m²"])

    def test_area_construida_sem_unidade_em_ato_de_edificacao(self):
        texto = """
        MATRÍCULA 15.857. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-15.857 - EDIFICAÇÃO. Casa residencial com a área construída de 42,10.
        O referido é verdade e dou fé.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["42,1 m²"])

    def test_area_construida_com_valor_por_extenso_entre_unidade_e_rotulo(self):
        texto = """
        MATRÍCULA 22.279. IMÓVEL: Lote 1, com área de 500m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-22.279 - EDIFICAÇÃO. Casa com 427,31m² (quatrocentos e vinte e sete
        metros e trinta e um centímetros quadrados) de área construída.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["427,31 m²"])

    def test_area_construida_com_mascara_em_texto_extenso(self):
        ruido = "descrição complementar " * 600
        texto = f"""
        MATRÍCULA 36.271. IMÓVEL: Lote 1, com área de 500m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-36.271 - EDIFICAÇÃO. {ruido} Casa com 82,37xxxx m², de área construída.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["82,37 m²"])

    def test_area_registral_historica_sem_acento(self):
        texto = """
        MATRÍCULA 13.868. IMÓVEL: Lote n.º 1, Quadra 2, com AREA DE 510,00M².
        PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["510 m²"])

    def test_area_registral_com_crase_e_tres_grupos_decimais(self):
        texto = """
        MATRÍCULA 13.145. IMÓVEL: Uma gleba de terras de campo com àrea de
        04,84,00ha, situada na zona rural. PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["4,84 ha"])

    def test_area_urbana_com_crase_e_tres_grupos_decimais(self):
        texto = """
        MATRÍCULA 29.049. IMÓVEL: Lote industrial com àrea de 1,141,35m².
        PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["1.141,35 m²"])

    def test_area_rural_historica_com_quatro_casas_no_ultimo_grupo(self):
        texto = """
        MATRÍCULA 13.148. IMÓVEL: Gleba rural com a área de 00,65,4074ha,
        ou 6.540,74m². PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["0,6541 ha"])

    def test_area_com_virgula_sobrando_antes_da_unidade(self):
        texto = """
        MATRÍCULA 25.849. IMÓVEL: Lote urbano com a área de 193,61,m².
        PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["193,61 m²"])

    def test_unidade_ha_digitada_com_acento(self):
        texto = """
        MATRÍCULA 19.417. IMÓVEL: Glebas rurais cadastradas no INCRA com a área
        de 203,2 há. PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["203,2 ha"])

    def test_demolicao_remove_area_construida_anterior(self):
        texto = """
        MATRÍCULA 801. IMÓVEL: Lote nº 1, Quadra 2, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-801 - EDIFICAÇÃO. Casa com 80m² de área construída.
        AV.02-801 - DEMOLIÇÃO. A casa, que possuía 80m² de área construída,
        foi demolida.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), [])

    def test_certidao_de_salto_na_numeracao_nao_e_matricula_ativa(self):
        texto = """
        CERTIFICO A OCORRÊNCIA DE SALTO NA NUMERAÇÃO SEQUENCIAL DE MATRÍCULAS,
        as quais deixaram de serem abertas, à época, sob os números de ordem
        13.486 a 13.845; razão porque não existem características de imóveis
        nesta Serventia sob os referidos números.
        """

        resultado = analisar_matricula(texto, numero_matricula="13500")["imovel"]

        self.assertEqual(
            resultado["situacao"],
            {"status": "INEXISTENTE", "origem": "Certidão de salto de numeração"},
        )
        self.assertEqual(valores_por_rotulo(resultado["identificacao"], "Matrícula"), ["13.500"])

    def test_area_rural_identificada_por_ibra_e_hectares_abreviados(self):
        texto = """
        MATRÍCULA 802. IMÓVEL: Quinhão de terras. IBRA nº 22.04.013-02145;
        com a área de 47,1ha. PROPRIETÁRIO: Pessoa Exemplo.
        """

        imovel = analisar_matricula(texto)["imovel"]

        self.assertEqual(imovel["tipo"], "RURAL")
        self.assertEqual(valores_por_rotulo(imovel["areas"], "Área"), ["47,1 ha"])

    def test_area_rural_historica_com_hectares_e_ares_sem_centiares(self):
        texto = """
        MATRÍCULA 805. IMÓVEL: Fazenda Exemplo, com a área
        806 (oitocentos e seis) hectares e 90 (noventa) ares.
        PROPRIETÁRIO: Pessoa Exemplo.
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área"), ["806,9 ha"])

    def test_area_construida_por_extenso_e_totalizacao_de_acrescimo(self):
        texto = """
        MATRÍCULA 803. IMÓVEL: Lote 1, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-803 - EDIFICAÇÃO. Casa com a área construída de 47 metros quadrados.
        AV.02-803 - ACRÉSCIMO. Área construída antiga de 47m² e acréscimo de
        58m², totalizando uma área de 105m².
        """

        areas = analisar_matricula(texto)["imovel"]["areas"]

        self.assertEqual(valores_por_rotulo(areas, "Área Construída"), ["105 m²"])

    def test_encerramento_ex_officio_e_formatos_alternativos_car_ccir(self):
        texto = """
        MATRÍCULA 804. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo.
        AV.01-804 - ATUALIZAÇÃO DO CCIR. Código do Imóvel Rural nº
        000.043.313.360-9; nº do CCIR: 12363256095.
        AV.02-804 - INSCRIÇÃO NO CAR. O imóvel foi inscrito no CAR sob o nº de
        GO-5213806-18D2.BC96.B2A1.45D1.8E37.F44D.95A6.3165.
        AV.03-804 - ENCERRAMENTO DE MATRÍCULA. Procede-se para constar o encerramento
        da presente matrícula, estando o imóvel matriculado sob o nº 18.948.
        """

        imovel = analisar_matricula(texto)["imovel"]

        self.assertEqual(imovel["situacao"]["status"], "ENCERRADA")
        self.assertEqual(valores_por_rotulo(imovel["cadastros"], "CCIR / código rural"), ["000.043.313.360-9"])
        self.assertEqual(
            valores_por_rotulo(imovel["cadastros"], "CAR"),
            ["GO-5213806-18D2.BC96.B2A1.45D1.8E37.F44D.95A6.3165"],
        )

    def test_endereco_historico_com_numero_por_extenso_beco_e_jardim(self):
        texto = """
        MATRÍCULA 805. IMÓVEL: Beco da Fileta, número 60, Jardim América,
        nesta cidade, com área de 300m². PROPRIETÁRIO: Pessoa Exemplo.
        """

        identificacao = analisar_matricula(texto)["imovel"]["identificacao"]

        self.assertEqual(valores_por_rotulo(identificacao, "Rua"), ["Beco da Fileta"])
        self.assertEqual(valores_por_rotulo(identificacao, "Número"), ["60"])
        self.assertEqual(valores_por_rotulo(identificacao, "Setor"), ["Jardim América"])

    def test_loteamento_sem_prefixo_setor_e_sem_aspas(self):
        texto = """
        MATRÍCULA 806. IMÓVEL: Lote 1 da Quadra 2, situado na Rua 06,
        do loteamento Vinícius Cândido, nesta cidade. PROPRIETÁRIO: Pessoa Exemplo.
        """

        identificacao = analisar_matricula(texto)["imovel"]["identificacao"]

        self.assertEqual(valores_por_rotulo(identificacao, "Setor"), ["Vinícius Cândido"])

    def test_denominacao_rural_prioriza_fazenda_e_descarta_especie_generica(self):
        casos = (
            ("Um sítio com casa, situado na Fazenda Serra, neste Município", "Fazenda Serra"),
            ("Fazenda Tamboril, desmembrada da Fazenda Serra", "Fazenda Tamboril"),
            ("Fazenda Três Barras e Vinagre, com área de 10ha", "Fazenda Três Barras e Vinagre"),
            ("Chácara São José, zona rural, com área de 2ha", "Chácara São José"),
        )
        for descricao, esperado in casos:
            with self.subTest(descricao=descricao):
                texto = f"MATRÍCULA 807. IMÓVEL: {descricao}. PROPRIETÁRIO: Pessoa Exemplo."
                identificacao = analisar_matricula(texto)["imovel"]["identificacao"]
                self.assertEqual(valores_por_rotulo(identificacao, "Nome"), [esperado])

    def test_imovel_rural_exibe_nome_sem_endereco_urbano(self):
        texto = """
        MATRÍCULA 39.802. IMÓVEL: Fazenda Santa Maria, situada na Rua Rural 1,
        n.º 75, Setor Rural, neste Município, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 111.222.333-44.
        """

        resultado = analisar_matricula(texto)["imovel"]
        identificacao = resultado["identificacao"]

        self.assertEqual(resultado["tipo"], "RURAL")
        self.assertEqual(valores_por_rotulo(identificacao, "Nome"), ["Fazenda Santa Maria"])
        self.assertFalse(valores_por_rotulo(identificacao, "Rua"))
        self.assertFalse(valores_por_rotulo(identificacao, "Número"))
        self.assertFalse(valores_por_rotulo(identificacao, "Setor"))

    def test_incra_moderno_por_codigo_do_imovel_rural_no_cabecalho(self):
        texto = """
        MATRÍCULA 808. IMÓVEL: Fazenda Bom Jardim, com área de 10ha. O imóvel
        encontra-se cadastrado no INCRA/SNCR conforme CCIR; código do imóvel rural:
        999.999.999.999-9. PROPRIETÁRIO: Pessoa Exemplo.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "INCRA"), ["999.999.999.999-9"])

    def test_incra_historico_seguido_de_virgula(self):
        texto = """
        MATRICULA 369. IMOVEL: Fazenda Cordeiro, com area de 8.160,00m2.
        Cadastrado no INCRA sob o n. 936.120.019.232, com 0,8ha, modulo 30,0.
        PROPRIETARIO: Pessoa Exemplo.
        """

        cadastros = analisar_matricula(texto)["imovel"]["cadastros"]

        self.assertEqual(valores_por_rotulo(cadastros, "INCRA"), ["936.120.019.232"])

    def test_vila_isolada_e_extraida_como_setor(self):
        texto = """
        MATRÍCULA 809. IMÓVEL: Rua 8, Vila São Pedro, nesta Cidade,
        constituído de um prédio e lote nº 3, quadra 33, com área de 518m².
        PROPRIETÁRIO: Pessoa Exemplo.
        """

        identificacao = analisar_matricula(texto)["imovel"]["identificacao"]

        self.assertEqual(valores_por_rotulo(identificacao, "Rua"), ["Rua 8"])
        self.assertEqual(valores_por_rotulo(identificacao, "Setor"), ["Vila São Pedro"])


if __name__ == "__main__":
    unittest.main()
