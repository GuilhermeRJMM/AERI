import unittest

from backend.app.servicos.analise_matricula import analisar_matricula


def valores_por_rotulo(itens, rotulo):
    return [item["valor"] for item in itens if item["rotulo"] == rotulo]


class TesteDadosImovel(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
