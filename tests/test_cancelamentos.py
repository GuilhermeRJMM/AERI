import unittest
from types import SimpleNamespace

from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.regras import REGRAS, classificar
from backend.app.servicos.analise_matricula import analisar_matricula


def ato(codigo, descricao):
    categoria, impacta = classificar(descricao)
    return SimpleNamespace(
        codigo=codigo,
        descricao=descricao,
        categoria=categoria,
        impacta_resultado=impacta,
        status="ATIVO",
        cancelado_por=None,
        cancela_atos=[],
    )


HIPOTECA = """
R.04-02 - Título: Cédula Rural Hipotecária. Objeto da garantia: Em hipoteca
cedular de 1º grau, o imóvel objeto desta matrícula.
"""

SUBSTITUICAO_PARCIAL = """
AV.05-02 - Liberação e Substituição da Área Hipotecada: foi liberada da
garantia hipotecária uma área com 14,52 hectares, permanecendo hipotecado o
remanescente do imóvel objeto da presente matrícula e do R.04-02, e deram em
garantia, em penhor cedular de 1º grau, 15 matrizes. A Cédula fica ratificada.
"""

CANCELAMENTO = """
AV.06-02 - Para constar que foi liberado do gravame hipotecário o R.04-02,
com autorização da Caixa Econômica do Estado de Goiás.
"""

RESTRICAO_URBANISTICA = """
AV.01-39.513 - TRASLADO/RESTRIÇÕES URBANÍSTICAS. O loteamento residencial
está sujeito às seguintes restrições urbanísticas: uso exclusivamente para
edificação residencial unifamiliar e vedação de edificações comerciais.
"""


class TesteCancelamentos(unittest.TestCase):
    def test_nenhuma_regra_classifica_restricao_como_onus(self):
        self.assertNotIn("RESTRIÇÃO", {regra["categoria"] for regra in REGRAS.values()})

    def test_alienacao_cancelada_com_restricao_resulta_so_em_publicidade(self):
        alienacao = ato("AV.01", "AV.01 - ALIENAÇÃO FIDUCIÁRIA do imóvel.")
        restricao = ato("AV.02", "AV.02 - CLÁUSULA RESTRITIVA de inalienabilidade.")
        cancelamento = ato("AV.03", "AV.03 - CANCELAMENTO da alienação do AV.01.")

        aplicar_cancelamentos([alienacao, restricao, cancelamento])

        self.assertEqual(alienacao.status, "CANCELADO")
        self.assertEqual(restricao.categoria, "PUBLICIDADE")
        self.assertFalse(restricao.impacta_resultado)
        self.assertFalse(any(
            item.categoria == "ÔNUS" and item.status == "ATIVO"
            for item in [alienacao, restricao, cancelamento]
        ))
        self.assertTrue(any(
            item.categoria == "PUBLICIDADE" and item.status == "ATIVO"
            for item in [alienacao, restricao, cancelamento]
        ))

    def test_restricao_urbanistica_e_publicidade_sem_onus(self):
        categoria, impacta = classificar(RESTRICAO_URBANISTICA)

        self.assertEqual(categoria, "PUBLICIDADE")
        self.assertFalse(impacta)

    def test_substituicao_parcial_nao_cria_onus_nem_cancela_hipoteca(self):
        hipoteca = ato("R.04", HIPOTECA)
        substituicao = ato("AV.05", SUBSTITUICAO_PARCIAL)

        aplicar_cancelamentos([hipoteca, substituicao])

        self.assertEqual(substituicao.categoria, "IGNORAR")
        self.assertFalse(substituicao.impacta_resultado)
        self.assertEqual(hipoteca.status, "ATIVO")
        self.assertTrue(hipoteca.impacta_resultado)

    def test_liberado_do_gravame_cancela_hipoteca_indicada(self):
        hipoteca = ato("R.04", HIPOTECA)
        substituicao = ato("AV.05", SUBSTITUICAO_PARCIAL)
        cancelamento = ato("AV.06", CANCELAMENTO)

        aplicar_cancelamentos([hipoteca, substituicao, cancelamento])

        self.assertEqual(cancelamento.categoria, "CANCELAMENTO")
        self.assertEqual(hipoteca.status, "CANCELADO")
        self.assertEqual(hipoteca.cancelado_por, "AV.06")
        self.assertFalse(hipoteca.impacta_resultado)
        self.assertEqual(substituicao.status, "ATIVO")

    def test_alienacao_fiduciaria_com_venda_no_titulo_e_onus(self):
        texto = """
        R.05 - DEVEDORES/FIDUCIANTES: Fulano. CREDORA/FIDUCIÁRIA: Banco.
        TÍTULO: Instrumento particular de financiamento para aquisição de imóvel,
        venda e compra e constituição de alienação fiduciária.
        OBJETO DA GARANTIA: Em Alienação Fiduciária, o imóvel desta matrícula.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_compra_financiada_nao_e_onus_alem_da_garantia_registrada(self):
        # Regressão (matrícula real 24.070): no financiamento imobiliário a
        # garantia está no NOME do contrato ("venda e compra mediante
        # financiamento garantido por alienação fiduciária"), mas esse ato é
        # o da aquisição -- quem constitui o gravame é o registro seguinte.
        # Classificar a compra como ônus criava um segundo gravame que o
        # cancelamento não alcançava (ele aponta para o registro da garantia),
        # e a matrícula seguia positiva mesmo com a alienação já cancelada.
        compra = """
        R1-24.070 - Nos termos CONTRATO POR INSTRUMENTO PARTICULAR, COM EFEITO DE
        ESCRITURA PÚBLICA DE VENDA E COMPRA DE IMÓVEL RESIDENCIAL NOVO MEDIANTE
        FINANCIAMENTO GARANTIDO POR ALIENAÇÃO FIDUCIÁRIA DE IMÓVEL-PESSOA FÍSICA-
        FGTS, o imóvel constante desta matrícula foi ADQUIRIDO POR Ricardo Messias
        Borges, CPF 971.640.201-59, por COMPRA FEITA a Construtora Exemplo Ltda,
        CNPJ 14.097.139/0001-00, pelo preço de R$90.000,00.
        """

        categoria, impacta = classificar(compra)

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_matricula_com_alienacao_cancelada_fica_negativa(self):
        compra = ato("R.01", """
        R1-24.070 - VENDA E COMPRA DE IMÓVEL RESIDENCIAL NOVO MEDIANTE FINANCIAMENTO
        GARANTIDO POR ALIENAÇÃO FIDUCIÁRIA. O imóvel foi ADQUIRIDO POR Ricardo
        Messias Borges, CPF 971.640.201-59, por COMPRA FEITA a Construtora Exemplo.
        """)
        garantia = ato("R.02", """
        R2-24.070 - DEVEDOR/FIDUCIANTE: Ricardo Messias Borges. CREDOR FIDUCIÁRIO:
        Banco do Brasil S/A. OBJETO DA GARANTIA: EM ALIENAÇÃO FIDUCIÁRIA o imóvel
        constante desta matrícula.
        """)
        cancelamento = ato("AV.03", """
        AV.03-24.070 - CANCELAMENTO DE ALIENAÇÃO FIDUCIÁRIA. Procede-se a presente
        averbação para constar que fica CANCELADA A ALIENAÇÃO FIDUCIÁRIA constante
        do R.02 desta matrícula.
        """)

        aplicar_cancelamentos([compra, garantia, cancelamento])

        self.assertEqual(compra.categoria, "IGNORAR")
        self.assertEqual(garantia.status, "CANCELADO")
        self.assertFalse(any(
            item.categoria == "ÔNUS" and item.status == "ATIVO"
            for item in (compra, garantia, cancelamento)
        ))

    def test_hipoteca_com_compra_e_venda_no_titulo_e_onus(self):
        texto = """
        R.05-12.011 - Nos termos do Contrato Particular de Compra e Venda e mútuo
        com obrigações e hipoteca, o imóvel objeto da presente matrícula foi dado
        em primeira e especial hipoteca à outorgada Credora Caixa Econômica Federal,
        em garantia do financiamento contraído.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_hipoteca_com_grau_por_extenso_e_numerico_entre_parenteses(self):
        texto = """
        R.08-93 - Título: Contrato Particular de Compra e Venda, Mútuo com
        Obrigações e Hipoteca. Objeto da garantia: Em primeira (1ª) e especial
        hipoteca, sem concorrência, o imóvel objeto da presente matrícula.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_compra_e_venda_com_titulo_de_hipoteca_sem_constituicao_expressa_ignora(self):
        texto = """
        R.04-12.011 - Nos termos do Contrato Particular de Compra e Venda e mútuo
        com obrigações e hipoteca, o imóvel objeto da presente matrícula foi adquirido
        por Fulano; por compra feita a Beltrano; financiamento concedido pela credora.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_aditivo_que_so_ratifica_vencimento_nao_cria_onus(self):
        texto = """
        AV.35-31.464 - ADITIVO. Nos termos do Aditivo de Retificação e
        Ratificação à Cédula de Crédito Bancário, registrada sob o R.29,
        procede-se a presente averbação para constar as seguintes alterações:
        VENCIMENTO: De 20.08.2026 para 20.05.2027. FORMA DE PAGAMENTO: uma
        parcela vencível em 20.05.2027. As partes ratificam ainda, em todos
        seus termos, as cláusulas, itens e demais condições estabelecidas na
        cédula aditada, inclusive as garantias nela constituídas, não
        expressamente alteradas pelo aditivo.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_aditivo_de_alteracao_de_prazo_sem_nova_garantia_nao_cria_onus(self):
        texto = """
        AV.49-287 - ALTERAÇÕES NO PRAZO DE VENCIMENTO E NA FORMA DE PAGAMENTO.
        Procede-se nos termos do Aditivo de Re-Ratificação à Cédula Rural
        Pignoratícia e Hipotecária para constar que o vencimento do R.46 foi
        prorrogado. Permanecem as demais cláusulas.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_retificacao_de_cpf_nao_herda_onus_mencionado(self):
        texto = """
        AV.19-10.597 - RETIFICAÇÃO DE CPF/MF EX-OFFICIO. Para constar que ao se
        efetuar o R.17 houve equívoco, sendo certo que a PENHORA registrada se
        refere aos direitos creditórios do negócio registrado no R.16.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_sobrenome_assuncao_em_inventario_nao_cria_onus(self):
        texto = """
        R.05-31.465 - INVENTÁRIO/PARTILHA. ADQUIRENTES: 1)- Valdomiro Avelino
        Vieira, inscrito no CPF/MF sob o n.º 089.368.111-34; 2)- Eni Avelina de
        Assunção, inscrita no CPF/MF sob o n.º 704.587.231-34, casada com Lazídio
        Dionízio de Assunção. IMÓVEL: O descrito na matrícula. FORMA DO TÍTULO:
        Escritura Pública de Arrolamento e Partilha.
        """

        categoria, impacta = classificar(texto)

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_assuncao_de_divida_continua_sendo_onus(self):
        categoria, impacta = classificar("AV.01 - ASSUNÇÃO DE DÍVIDA garantida pelo imóvel.")

        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_cancelamento_informa_ato_cancelado_mesmo_no_ato_cancelador(self):
        alienacao = ato("R.05", "R.05 - ALIENAÇÃO FIDUCIÁRIA. OBJETO DA GARANTIA: Em Alienação Fiduciária.")
        cancelamento = ato("AV.08", "AV.08 - CANCELAMENTO. Fica cancelada a alienação fiduciária constante do R.05 desta matrícula.")

        aplicar_cancelamentos([alienacao, cancelamento])

        self.assertEqual(alienacao.status, "CANCELADO")
        self.assertEqual(cancelamento.cancela_atos, ["R.05"])


    def test_cancelamento_reconhece_virgula_entre_tipo_e_numero(self):
        hipoteca = ato("R.02", "R.02 - Cedula Rural Pignoraticia e Hipotecaria. Objeto da garantia: Em hipoteca cedular.")
        cancelamento = ato("AV.04", "AV.04 - Cancelamento. Pagamento total da divida constante do R-,02 supra, averba-se o cancelamento daquele Registro.")

        aplicar_cancelamentos([hipoteca, cancelamento])

        self.assertEqual(hipoteca.status, "CANCELADO")
        self.assertEqual(hipoteca.cancelado_por, "AV.04")
        self.assertEqual(cancelamento.cancela_atos, ["R.02"])

    def test_cancelamento_reconhece_referencia_grudada_no_numero(self):
        hipoteca = ato("R.02", "R.02 - Cedula Rural Pignoraticia e Hipotecaria. Objeto da garantia: Em hipoteca cedular.")
        cancelamento = ato("AV.03", "AV.03 - Cancelamento. Para que o registro R2-451 fique cancelado.")

        aplicar_cancelamentos([hipoteca, cancelamento])

        self.assertEqual(hipoteca.status, "CANCELADO")
        self.assertEqual(hipoteca.cancelado_por, "AV.03")
        self.assertEqual(cancelamento.cancela_atos, ["R.02"])

    def test_cancelamentos_da_matricula_10151_aceitam_sufixo_pontuado(self):
        historicos = [
            ato(
                f"R.{numero}",
                f"R.{numero}-10.151 - CÉDULA RURAL HIPOTECÁRIA. "
                "OBJETO DA GARANTIA: Em hipoteca cedular, o imóvel.",
            )
            for numero in (2, 3, 4, 11, 14, 15, 17, 18, 19, 20, 21, 22, 23)
        ]
        cancelamentos = [
            ato("AV.09", "AV.09-10.151 - CANCELAMENTO da hipoteca do R-4-10.151."),
            ato("AV.10", "AV.10-10.151 - CANCELAMENTO das hipotecas dos R-2-10.151 e R-3-10.151."),
            ato("AV.12", "AV.12-10.151 - CANCELAMENTO da hipoteca do R-11-10.151."),
            ato("AV.16", "AV.16-10.151 - CANCELAMENTO das hipotecas do R-14 e R-15-10.151."),
            ato("AV.24", "AV.24-10.151 - CANCELAMENTO da hipoteca do R-22-10.151."),
            ato("AV.25", "AV.25-10.151 - CANCELAMENTO da hipoteca do R-23-10.151."),
            ato("AV.26", "AV.26-10.151 - CANCELAMENTO da hipoteca do R-17-10.151."),
            ato("AV.27", "AV.27-10.151 - CANCELAMENTO da hipoteca do R-18-10.151."),
            ato("AV.28", "AV.28-10.151 - CANCELAMENTO da hipoteca do R-19-10.151."),
            ato("AV.29", "AV.29-10.151 - CANCELAMENTO da hipoteca do R-20-10.151."),
            ato("AV.30", "AV.30-10.151 - CANCELAMENTO da hipoteca do R-21-10.151."),
        ]
        penhoras_atuais = [
            ato("R.46", "R.46-10.151 - PENHORA do imóvel objeto da matrícula."),
            ato("R.51", "R.51-10.151 - PENHORA do imóvel objeto da matrícula."),
        ]

        aplicar_cancelamentos(historicos + cancelamentos + penhoras_atuais)

        self.assertTrue(all(item.status == "CANCELADO" for item in historicos))
        self.assertTrue(all(item.status == "ATIVO" for item in penhoras_atuais))

    def test_referencia_pontuada_de_outra_matricula_nao_cancela_ato_local(self):
        hipoteca = ato(
            "R.04",
            "R.04-10.151 - CÉDULA RURAL HIPOTECÁRIA. "
            "OBJETO DA GARANTIA: Em hipoteca cedular, o imóvel.",
        )
        cancelamento = ato(
            "AV.09",
            "AV.09-10.151 - CANCELAMENTO do ato R-4-10.152.",
        )

        aplicar_cancelamentos([hipoteca, cancelamento])

        self.assertEqual(hipoteca.status, "ATIVO")


    def test_adjudicacao_pode_cancelar_penhora_na_nota(self):
        penhora = ato("R.03", "R.03 - PENHORA do imóvel objeto da matrícula.")
        adjudicacao = ato(
            "R.07",
            "R.07 - ADJUDICAÇÃO. O imóvel coube ao adjudicante. *NOTA: fica cancelada a penhora constante do R.03 supra.",
        )

        aplicar_cancelamentos([penhora, adjudicacao])

        self.assertEqual(penhora.status, "CANCELADO")
        self.assertEqual(penhora.cancelado_por, "R.07")
        self.assertEqual(adjudicacao.cancela_atos, ["R.03"])

    def test_cancelamento_por_titulo_reconhece_tipos_de_onus_alem_do_subconjunto_antigo(self):
        # TIPOS_CANCELAVEIS agora deriva de TIPOS_ONUS (regras.py) em vez de
        # uma lista mantida à mão que ficava atrás dela. ANTICRESE é um tipo
        # de ônus que nunca esteve na lista antiga -- sem a referência
        # numérica explícita (R.02), o cancelamento só é encontrado pelo
        # título se o tipo for reconhecido em TIPOS_CANCELAVEIS.
        anticrese = ato("R.02", "R.02-49 - ANTICRESE do imóvel objeto da matrícula.")
        cancelamento = ato(
            "AV.03",
            "AV.03-49 - CANCELAMENTO DE ANTICRESE. Fica cancelada a anticrese constante desta matrícula.",
        )

        aplicar_cancelamentos([anticrese, cancelamento])

        self.assertEqual(anticrese.status, "CANCELADO")
        self.assertEqual(anticrese.cancelado_por, "AV.03")

    def test_erro_de_referencia_nao_cancela_outro_cancelamento(self):
        hipoteca = ato("R.02", "R.02-49 - HIPOTECA do imóvel.")
        cancelamento_antigo = ato("AV.03", "AV.03-49 - CANCELAMENTO da hipoteca do R.02.")
        usufruto = ato("R.14", "R.14-49 - USUFRUTO VITALÍCIO em favor de duas pessoas.")
        cancelamento_usufruto = ato(
            "AV.15",
            "AV.15-49 - CANCELAMENTO DE USUFRUTO. Fica cancelado o usufruto constante do R.03 desta matrícula.",
        )

        aplicar_cancelamentos([hipoteca, cancelamento_antigo, usufruto, cancelamento_usufruto])

        self.assertEqual(cancelamento_antigo.status, "ATIVO")
        self.assertEqual(usufruto.status, "CANCELADO")
        self.assertEqual(cancelamento_usufruto.cancela_atos, ["R.14"])

    def test_referencia_de_outra_matricula_nao_cancela_ato_local_e_abreviada_cancela(self):
        hipoteca_23 = ato("R.23", "R.23-27 - Objeto da garantia: em hipoteca, o imóvel.")
        hipoteca_39 = ato("R.39", "R.39-27 - Objeto da garantia: em hipoteca, o imóvel.")
        cancelamento = ato(
            "AV.46",
            "AV.46-27 - CANCELAMENTO. Os R.23-31 e 39-27 ficam cancelados.",
        )

        aplicar_cancelamentos([hipoteca_23, hipoteca_39, cancelamento])

        self.assertEqual(hipoteca_23.status, "ATIVO")
        self.assertEqual(hipoteca_39.status, "CANCELADO")
        self.assertEqual(cancelamento.cancela_atos, ["R.39"])

    def test_referencia_a_numero_de_livro_nao_e_tratada_como_codigo_de_ato(self):
        hipoteca = ato("R.03", "R.03-45 - HIPOTECA atual.")
        cancelamento = ato(
            "AV.07",
            "AV.07-45 - CANCELAMENTO do registro R-3.390, fls. 153 do Livro 9-E.",
        )

        aplicar_cancelamentos([hipoteca, cancelamento])

        self.assertEqual(hipoteca.status, "ATIVO")
        self.assertEqual(cancelamento.cancela_atos, [])

    def test_exclusao_integral_da_garantia_cancela_onus_indicado(self):
        hipoteca = ato("R.13", "R.13-71 - Objeto da garantia: em hipoteca, o imóvel.")
        exclusao = ato(
            "AV.14",
            "AV.14-71 - EXCLUSÃO DE BENS VINCULADOS. Fica excluído da garantia hipotecária o R.13 supra.",
        )

        aplicar_cancelamentos([hipoteca, exclusao])

        self.assertEqual(exclusao.categoria, "CANCELAMENTO")
        self.assertEqual(hipoteca.status, "CANCELADO")

    def test_prorrogacao_sem_nova_constituicao_nao_cria_onus(self):
        categoria, impacta = classificar(
            "AV.21-27 - PRORROGAÇÃO DE PRAZO E RETIFICAÇÃO DA DENOMINAÇÃO DA CÉDULA. "
            "O vencimento do R.19 fica prorrogado e a cédula passa a denominar-se Cédula Rural Hipotecária."
        )

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_liberacao_do_imovel_vinculado_cancela_hipoteca(self):
        hipoteca = ato("R.09", "R.09-150 - Objeto da garantia: em hipoteca, o imóvel.")
        liberacao = ato(
            "AV.11",
            "AV.11-150 - LIBERAÇÃO DO IMÓVEL VINCULADO. O imóvel constante do R.09 "
            "é liberado da garantia e a cédula passa a ser apenas pignoratícia.",
        )

        aplicar_cancelamentos([hipoteca, liberacao])

        self.assertEqual(liberacao.categoria, "CANCELAMENTO")
        self.assertEqual(hipoteca.status, "CANCELADO")

    def test_desvinculacao_integral_cancela_garantias_referidas(self):
        hipoteca = ato("AV.04", "AV.04-233 - Objeto da garantia: em hipoteca, o imóvel.")
        desvinculacao = ato(
            "AV.05",
            "AV.05-233 - DESVINCULAÇÃO DE IMÓVEL, GARANTIA HIPOTECÁRIA. Em virtude "
            "da garantia objeto da AV.04, o imóvel ficou desvinculado de qualquer garantia.",
        )

        aplicar_cancelamentos([hipoteca, desvinculacao])

        self.assertEqual(desvinculacao.categoria, "CANCELAMENTO")
        self.assertEqual(hipoteca.status, "CANCELADO")

    def test_cancelamento_de_assuncao_cancela_garantias_originarias_referidas(self):
        antiga_1 = ato("AV.01", "AV.01-233 - Objeto da garantia: em hipoteca, o imóvel.")
        antiga_2 = ato("R.02", "R.02-233 - Objeto da garantia: em hipoteca, o imóvel.")
        assuncao = ato(
            "AV.04",
            "AV.04-233 - CONFISSÃO E ASSUNÇÃO DE DÍVIDAS COM GARANTIA HIPOTECÁRIA. "
            "A dívida constante da AV.01 e do R.02 foi assumida com garantia sobre o imóvel.",
        )
        desvinculacao = ato(
            "AV.05",
            "AV.05-233 - DESVINCULAÇÃO DE IMÓVEL. O imóvel objeto da garantia da AV.04 "
            "ficou desvinculado de qualquer garantia.",
        )

        aplicar_cancelamentos([antiga_1, antiga_2, assuncao, desvinculacao])

        self.assertEqual([antiga_1.status, antiga_2.status, assuncao.status], ["CANCELADO"] * 3)
        self.assertEqual(desvinculacao.cancela_atos, ["AV.04", "AV.01", "R.02"])

    def test_insercao_de_qualificacao_nao_repete_alienacao_fiduciaria(self):
        categoria, impacta = classificar(
            "AV.05-165 - INSERÇÃO DE DADOS DE QUALIFICAÇÃO PESSOAL, EX-OFFICIO. "
            "Conforme Contrato de Mútuo com Alienação Fiduciária, a proprietária "
            "é inscrita no CPF sob o número indicado."
        )

        self.assertEqual(categoria, "IGNORAR")
        self.assertFalse(impacta)

    def test_vinculo_historico_com_cedulas_hipotecarias_e_onus(self):
        categoria, impacta = classificar(
            "AV.01-56 - O imóvel está vinculado ao banco pelas cédulas rurais "
            "pignoratícias e hipotecárias inscritas sob os números indicados."
        )

        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_cancelamento_parcial_de_registros_legados_mantem_vinculo_ativo(self):
        vinculo = ato(
            "AV.01",
            "AV.01-297 - O imóvel está vinculado pelas cédulas hipotecárias, "
            "inscritas sob os n.ºs 2.321, 3.895 e 3.920, fls. 10, Livro 9-D.",
        )
        parcial = ato(
            "AV.03",
            "AV.03-297 - CANCELAMENTO. Fica cancelado o registro 2.321, constante da AV.01.",
        )

        aplicar_cancelamentos([vinculo, parcial])

        self.assertEqual(vinculo.status, "ATIVO")
        self.assertEqual(parcial.cancela_atos, ["AV.01"])

    def test_ultimo_cancelamento_dos_registros_legados_extingue_vinculo(self):
        vinculo = ato(
            "AV.01",
            "AV.01-56 - O imóvel está vinculado pelas cédulas hipotecárias, "
            "inscritas sob os n.ºs 3.072, 3.327 e 3.578, fls. 10, Livro 9-E.",
        )
        parcial = ato("AV.02", "AV.02-56 - CANCELAMENTO do registro 3.072, constante da AV.01.")
        final = ato("AV.03", "AV.03-56 - CANCELAMENTO dos registros 3.327 e 3.578, constantes da AV.01.")

        aplicar_cancelamentos([vinculo, parcial, final])

        self.assertEqual(vinculo.status, "CANCELADO")
        self.assertEqual(vinculo.cancelado_por, "AV.03")
        self.assertEqual(final.cancela_atos, ["AV.01"])

    def test_quitacao_do_pacto_comissorio_cancela_publicidade(self):
        pacto = ato("AV.17", "AV.17-27 - PACTO COMISSÓRIO que vincula o imóvel.")
        quitacao = ato(
            "AV.18",
            "AV.18-27 - QUITAÇÃO DE PROMISSÓRIA E PACTO COMISSÓRIO. "
            "Autoriza o seu desvinculamento, bem como o pacto objeto da AV.17.",
        )

        aplicar_cancelamentos([pacto, quitacao])

        self.assertEqual(quitacao.categoria, "CANCELAMENTO")
        self.assertEqual(pacto.status, "CANCELADO")

    def test_levantamento_de_penhora_prevalece_sobre_mencao_ao_gravame(self):
        categoria, impacta = classificar(
            "AV.06 - LEVANTAMENTO DE PENHORA. Fica cancelado o R.04 em virtude da quitação."
        )
        self.assertEqual((categoria, impacta), ("CANCELAMENTO", False))

    def test_liberacao_ou_substituicao_nao_cria_nova_hipoteca(self):
        textos = (
            "AV.25 - LIBERAÇÃO DE HIPOTECA. Procede-se para liberar o imóvel do R.22.",
            "AV.10 - SUBSTITUIÇÃO DE BENS VINCULADOS. Foi liberado do gravame hipotecário o R.08.",
            "AV.03 - Por aditivo, ficou excluído da AV.01 o registro hipotecário indicado.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("CANCELAMENTO", False))

    def test_hipoteca_historica_sem_titulo_padronizado_e_onus(self):
        categoria, impacta = classificar(
            "AV.01 - O imóvel constante da presente matrícula foi hipotecado pelos "
            "proprietários ao Banco do Brasil, conforme cédulas rurais hipotecárias."
        )
        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_registro_de_penhora_prevalece_sobre_mencao_a_execucao(self):
        categoria, impacta = classificar(
            "R.07 - Nos autos da ação de execução, procedo ao registro da Penhora "
            "do imóvel para assegurar o pagamento da dívida."
        )
        self.assertEqual(categoria, "ÔNUS")
        self.assertTrue(impacta)

    def test_retificacao_ex_officio_nao_repete_garantia(self):
        categoria, impacta = classificar(
            "AV.74 - RETIFICAÇÃO EX-OFFICIO. Corrige-se o objeto das garantias "
            "hipotecárias dos R.48 e R.49, que corresponde a 1.306,80ha."
        )
        self.assertEqual((categoria, impacta), ("IGNORAR", False))

    def test_alienacao_fiduciaria_superveniente_e_onus(self):
        categoria, impacta = classificar(
            "R.105 - ALIENAÇÃO FIDUCIÁRIA SUPERVENIENTE. PROPRIETÁRIO/FIDUCIANTE: "
            "Pessoa Exemplo. CREDOR/FIDUCIÁRIO: Banco Exemplo."
        )
        self.assertEqual((categoria, impacta), ("ÔNUS", True))

    def test_reserva_de_usufruto_em_doacao_e_onus(self):
        categoria, impacta = classificar(
            "R.04 - DOAÇÃO. A doadora reserva para si o direito ao usufruto "
            "vitalício sobre a totalidade do imóvel doado."
        )
        self.assertEqual((categoria, impacta), ("ÔNUS", True))

    def test_redacoes_historicas_de_cancelamento(self):
        textos = (
            "AV.05 - PERMUTA DE BENS APENHADOS. O imóvel foi substituído na garantia.",
            "AV.35 - LIBERAÇÃO DE BENS APENHADOS. Fica liberado o imóvel do R.32.",
            "AV.43 - SUBSTITUIÇÃO DE GARANTIA. Fica liberado do gravame o R.26.",
            "R.08 - DESISTÊNCIA DE USUFRUTO. A usufrutuária renuncia ao R.04.",
            "AV.07 - RENÚNCIA DE USUFRUTO. Os usufrutuários renunciaram ao R.04.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("CANCELAMENTO", False))

    def test_procedido_ao_registro_da_penhora_e_onus(self):
        categoria, impacta = classificar(
            "R.09 - Nos autos da execução, foi procedido ao Registro da penhora "
            "do imóvel constante da presente matrícula."
        )
        self.assertEqual((categoria, impacta), ("ÔNUS", True))

    def test_hipoteca_historica_abreviada_e_onus(self):
        textos = (
            "AV.01 - Hipoteca. Ditos bens já se acham vinculados ao banco pela CRPH.",
            "AV.01 - Hipotecas. Ditos bens já se acham hipotecados em 1º grau pela CRH.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_mutuo_ou_confissao_com_garantia_hipotecaria_e_onus(self):
        textos = (
            "R.09 - Mútuo com Obrigações e Hipoteca. Objeto da garantia: "
            "em 1ª e especial hipoteca, o imóvel desta matrícula.",
            "AV.02 - Confissão de dívidas com garantia pignoratícia e hipotecária.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_alteracao_financeira_sem_nova_garantia_nao_e_onus(self):
        categoria, impacta = classificar(
            "AV.13 - ALTERAÇÃO DE ENCARGOS FINANCEIROS. O prazo do R.11 foi prorrogado."
        )
        self.assertEqual((categoria, impacta), ("IGNORAR", False))

    def test_liberacao_e_permuta_de_bens_vinculados_cancelam_onus(self):
        textos = (
            "AV.15 - Foram liberadas do gravame hipotecário os R.06 e R.09.",
            "AV.122 - PERMUTA DE BENS VINCULADOS. Foi liberado da garantia o R.78.",
            "AV.24 - PERMUTA DE BENS HIPOTECADOS. Foi liberado da garantia o imóvel do R.21.",
            "AV.07 - É liberado da garantia o imóvel constante do R.03.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("CANCELAMENTO", False))

    def test_confissao_e_assuncao_com_garantias_e_onus(self):
        texto = (
            "AV.04 - CONFISSÃO E ASSUNÇÃO DE DÍVIDAS COM GARANTIAS PIGNORATÍCIA "
            "E HIPOTECÁRIA. Os assuntores assumiram a dívida garantida pelo imóvel."
        )
        self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_alteracao_de_credor_e_comissao_nao_criam_onus(self):
        textos = (
            "AV.19 - ALTERAÇÃO DE CREDOR. A credora do contrato de abertura de crédito foi incorporada.",
            "AV.10 - COMISSÃO DE PERMANÊNCIA. Retifica-se cláusula do contrato com hipoteca.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("IGNORAR", False))

    def test_imovel_ja_hipotecado_em_abertura_historica_e_onus(self):
        texto = "AV.01 - O imóvel objeto da presente matrícula está hipotecado à Caixa Econômica."
        self.assertEqual(classificar(texto), ("ÔNUS", True))


    def test_compra_e_venda_com_mutuo_e_alienacao_fiduciaria_e_onus(self):
        texto = (
            "R.05 - CONTRATO POR INSTRUMENTO PARTICULAR DE COMPRA E VENDA DE "
            "UNIDADE ISOLADA E MÚTUO COM OBRIGAÇÕES E ALIENAÇÃO FIDUCIÁRIA. "
            "O imóvel foi adquirido pelos compradores e devedores fiduciantes."
        )
        self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_aditivo_financeiro_nao_cria_novo_onus(self):
        texto = (
            "AV.07 - TRASLADO/ADITIVO. Conforme Aditivo de Retificação e "
            "Ratificação à Cédula Rural Hipotecária, altera-se o vencimento e "
            "a forma de pagamento. Permanecem ratificadas as garantias anteriores."
        )
        self.assertEqual(classificar(texto), ("IGNORAR", False))

    def test_aditivo_que_inclui_hipoteca_cria_onus(self):
        texto = (
            "AV.03 - ADITIVO DE RE-RATIFICAÇÃO. Foi retificado o grau e incluída "
            "a hipoteca cedular de terceiro grau sobre o imóvel."
        )
        self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_atualizacao_de_ccir_nao_herda_usufruto_da_escritura_citada(self):
        texto = (
            "AV.13 - ATUALIZAÇÃO DO CERTIFICADO DE CADASTRO DE IMÓVEL RURAL - CCIR. "
            "Nos termos do requerimento contido na Escritura Pública de Doação com "
            "Reserva de Usufruto Vitalício, atualiza-se o código cadastral."
        )
        self.assertEqual(classificar(texto), ("IGNORAR", False))

    def test_clausula_de_incomunicabilidade_nao_herda_usufruto_da_origem(self):
        texto = (
            "AV.10 - CLÁUSULA DE INCOMUNICABILIDADE. Conforme escritura de Doação "
            "com Reserva de Usufruto Vitalício, grava-se a cláusula restritiva."
        )
        self.assertEqual(classificar(texto), ("PUBLICIDADE", False))

    def test_cancelamento_de_hipoteca_prevalece_sobre_aditivo_citado(self):
        texto = (
            "AV.04 - CANCELAMENTO DE HIPOTECA POR SUBSTITUIÇÃO DO IMÓVEL HIPOTECADO. "
            "Nos termos do aditivo de retificação e ratificação à Cédula de Crédito Rural."
        )
        self.assertEqual(classificar(texto), ("CANCELAMENTO", False))

    def test_aditivo_de_re_ratificacao_sem_nova_garantia_nao_cria_onus(self):
        texto = (
            "AV.25 - RE-RATIFICAÇÃO DE REGISTRO. Nos termos do ADITIVO DE "
            "RE-RATIFICAÇÃO À CÉDULA RURAL PIGNORATÍCIA E HIPOTECÁRIA, "
            "ficam ratificadas as condições anteriores."
        )
        self.assertEqual(classificar(texto), ("IGNORAR", False))

    def test_titulo_constitutivo_prevalece_sobre_cadastro_citado_no_corpo(self):
        textos = (
            "R.04 - ARRESTO. Nos termos do mandado, consta também o CCIR do imóvel.",
            "R.03 - SEQUESTRO E INDISPONIBILIDADE DE BENS. Consta o CEP da parte.",
            "R.15 - PENHORA. Nos termos do mandado de execução, consta o CCIR.",
            "R.34 - COMPRA E VENDA COM INSTITUIÇÃO DE USUFRUTO VITALÍCIO. Consta o CEP.",
            "R.03 - CONTRATO DE VENDA E COMPRA COM ALIENAÇÃO FIDUCIÁRIA. Consta o CCIR.",
            "R.07 - DEVEDOR: Pessoa. TÍTULO: CÉDULA RURAL HIPOTECÁRIA. Consta o CAR.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_indicacao_de_graus_e_credores_nao_duplica_hipotecas(self):
        texto = (
            "AV.45 - INDICAÇÃO GRAUS E CREDORES. Indicam-se os graus atualizados "
            "das hipotecas já constantes dos registros anteriores."
        )
        self.assertEqual(classificar(texto), ("IGNORAR", False))


    def test_hipoteca_legal_historica_e_onus(self):
        texto = (
            "R.01 - Nos termos do mandado judicial, sobre o imóvel foi instituída "
            "a Hipoteca legal de primeiro grau sem concorrência de terceiros."
        )
        self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_traslado_informa_imovel_que_se_encontra_hipotecado(self):
        texto = (
            "AV.01 - HIPOTECA. O imóvel objeto da presente matrícula encontra-se "
            "hipotecado em primeiro grau conforme registro da matrícula de origem."
        )
        self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_cancelamento_de_arresto_nao_vira_novo_onus(self):
        self.assertEqual(
            classificar(
                "AV.05 - CANCELAMENTO DE ARRESTO. Certifico que fica cancelado o R.04."
            ),
            ("CANCELAMENTO", False),
        )

    def test_cancelamento_generico_com_garantia_citada_nao_vira_onus(self):
        self.assertEqual(
            classificar(
                "AV.11 - CANCELAMENTO: Nos termos da escritura de abertura de crédito "
                "com garantia hipotecária, fica cancelado o R.10."
            ),
            ("CANCELAMENTO", False),
        )

    def test_retificacao_de_penhora_nao_cria_segundo_onus(self):
        self.assertEqual(
            classificar(
                "AV.11 - RETIFICAÇÃO: Somente 50% do imóvel objeto do R.10 foi dado em penhora."
            ),
            ("IGNORAR", False),
        )

    def test_aditivo_que_substitui_bem_e_da_imovel_em_hipoteca_cria_onus(self):
        texto = (
            "R.20 - TÍTULO: Aditivo de Re-Ratificação à Cédula Rural. "
            "Em substituição da garantia anterior, foi dado em hipoteca cedular "
            "de segundo grau o imóvel desta matrícula."
        )

        self.assertEqual(classificar(texto), ("ÔNUS", True))

    def test_atualizacao_de_designacao_nao_herda_usufruto_citado(self):
        texto = (
            "AV.06-914 - ATUALIZAÇÃO DE DESIGNAÇÃO CADASTRAL DO IMÓVEL. "
            "Nos termos da Escritura de Inventário, Partilha e Doação com "
            "Reserva de Usufruto, atualiza-se o número cadastral."
        )
        self.assertEqual(classificar(texto), ("IGNORAR", False))

    def test_obito_e_adjudicacao_nao_repetem_usufruto_da_escritura(self):
        textos = (
            "AV.07-914 - ÓBITO. Conforme Escritura de Doação com Reserva de Usufruto, faleceu o titular.",
            "R.08-914 - ADJUDICAÇÃO. Conforme Escritura de Doação com Reserva de Usufruto, coube o imóvel ao adjudicante.",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertEqual(classificar(texto), ("IGNORAR", False))

    def test_liberacao_e_desvinculacao_nao_cria_nova_hipoteca(self):
        texto = (
            "AV.04-32 - DESVINCULAÇÃO E LIBERAÇÃO DE IMÓVEL. O credor liberou e "
            "desvinculou da garantia hipotecária o imóvel objeto desta matrícula."
        )
        self.assertEqual(classificar(texto), ("CANCELAMENTO", False))

    def test_venda_nao_duplica_alienacao_registrada_no_ato_seguinte(self):
        texto = """
        MATRÍCULA 1.330. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Inicial.
        R.04-1.330 - Protocolo n.º 164.207. VENDA E COMPRA. TÍTULO: Instrumento
        Particular de Venda e Compra com Garantia de Alienação Fiduciária.
        ADQUIRENTE: Pessoa Compradora.
        R.05-1.330 - Protocolo n.º 164.207. ALIENAÇÃO FIDUCIÁRIA. DEVEDOR
        FIDUCIANTE: Pessoa Compradora. CREDOR FIDUCIÁRIO: Banco Exemplo.
        OBJETO DA GARANTIA: Em alienação fiduciária, o imóvel desta matrícula.
        """
        resultado = analisar_matricula(texto)
        alienacoes = [
            ato for ato in resultado["atos"]
            if ato.get("tipo_onus") == "ALIENAÇÃO FIDUCIÁRIA"
        ]
        self.assertEqual(["R.05"], [ato["codigo"] for ato in alienacoes])

    def test_matricula_22684_venda_sem_protocolo_nao_duplica_alienacao(self):
        texto = """
        MATRÍCULA 22.684. IMÓVEL: Lote 27. PROPRIETÁRIOS: Pessoas iniciais.
        R.01-22.684 - CONTRATO POR INSTRUMENTO PARTICULAR DE COMPRA E VENDA
        DE TERRENO, MÚTUO PARA OBRAS E ALIENAÇÃO FIDUCIÁRIA EM GARANTIA.
        O imóvel foi adquirido por Elisabete Camilo do Nascimento Batista e
        João Luiz Batista.
        R.02-22.684 - DEVEDORES/FIDUCIANTES: Elisabete Camilo do Nascimento
        Batista e João Luiz Batista. CREDORA/FIDUCIÁRIA: Caixa Econômica
        Federal. TÍTULO: contrato de compra e venda e alienação fiduciária.
        OBJETO DA GARANTIA: em alienação fiduciária, o imóvel desta matrícula.
        AV.05-22.684 - CANCELAMENTO DE ALIENAÇÃO FIDUCIÁRIA. Fica cancelada a
        alienação fiduciária constante do R.02 desta matrícula.
        R.07-22.684 - ALIENAÇÃO FIDUCIÁRIA. DEVEDOR/FIDUCIANTE: Gustavo
        Cardoso Porto. CREDORA/FIDUCIÁRIA: Caixa Econômica Federal.
        OBJETO DA GARANTIA: o imóvel desta matrícula.
        """
        resultado = analisar_matricula(texto)
        alienacoes = {
            ato["codigo"]: ato for ato in resultado["atos"]
            if ato.get("tipo_onus") == "ALIENAÇÃO FIDUCIÁRIA"
        }

        self.assertNotIn("R.01", [ato["codigo"] for ato in resultado["atos"]])
        self.assertEqual({"R.02", "R.07"}, set(alienacoes))
        self.assertEqual("CANCELADO", alienacoes["R.02"]["status"])
        self.assertEqual("ATIVO", alienacoes["R.07"]["status"])

    def test_leiloes_negativos_extinguem_alienacao_sem_referencia(self):
        texto = """
        MATRÍCULA 3.538. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Devedora.
        R.07-3.538 - ALIENAÇÃO FIDUCIÁRIA. DEVEDOR FIDUCIANTE: Pessoa Devedora.
        CREDORA FIDUCIÁRIA: Caixa Exemplo. OBJETO DA GARANTIA: Em alienação
        fiduciária, o imóvel desta matrícula.
        AV.10-3.538 - LEILÕES NEGATIVOS / EXTINÇÃO DA DÍVIDA ORIGINÁRIA. Foram
        realizados dois leilões públicos, sendo negativo o resultado de ambos,
        e a dívida originária na qual se constituiu a garantia da alienação
        fiduciária foi considerada extinta.
        """
        resultado = analisar_matricula(texto)
        alienacao = next(ato for ato in resultado["atos"] if ato["codigo"] == "R.07")
        self.assertEqual("CANCELADO", alienacao["status"])
        self.assertEqual("AV.10", alienacao["cancelado_por"])
        self.assertEqual("NEGATIVA PARA ÔNUS", resultado["resultado"])

    def test_matricula_18552_designacao_nao_herda_alienacao_da_escritura(self):
        texto = """
        MATRÍCULA 18.552. IMÓVEL: Lote 15, Quadra 25, Setor Aeroporto.
        PROPRIETÁRIO: Rafael Rodrigues Romano.
        AV.03-18.552 - DESIGNAÇÃO CADASTRAL DO IMÓVEL. Nos termos do
        requerimento contido na Escritura Pública de Confissão de Dívida com
        Constituição de Garantia em Alienação Fiduciária, procede-se a esta
        averbação para constar o CCI n.º 126.614.
        R.04-18.552 - ALIENAÇÃO FIDUCIÁRIA. DEVEDOR FIDUCIANTE: Rafael
        Rodrigues Romano. CREDOR FIDUCIÁRIO: Dacarto Benvindo de Carvalho.
        OBJETO DA GARANTIA: o imóvel desta matrícula.
        AV.06-18.552 - CANCELAMENTO DE ALIENAÇÃO FIDUCIÁRIA. Procede-se ao
        cancelamento da alienação fiduciária objeto do R.04 desta matrícula.
        """
        resultado = analisar_matricula(texto)
        codigos = [ato["codigo"] for ato in resultado["atos"]]
        alienacao = next(ato for ato in resultado["atos"] if ato["codigo"] == "R.04")

        self.assertNotIn("AV.03", codigos)
        self.assertEqual("CANCELADO", alienacao["status"])
        self.assertEqual("AV.06", alienacao["cancelado_por"])
        self.assertEqual("NEGATIVA PARA ÔNUS", resultado["resultado"])

    def test_alienacao_verdadeira_nao_e_ignorada_por_mencionar_designacao(self):
        texto = """
        MATRÍCULA 1. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Devedora.
        R.04-1 - ALIENAÇÃO FIDUCIÁRIA. DEVEDOR FIDUCIANTE: Pessoa Devedora.
        CREDOR FIDUCIÁRIO: Banco Exemplo. Atualiza-se também a designação
        cadastral do imóvel. OBJETO DA GARANTIA: o imóvel desta matrícula.
        """
        resultado = analisar_matricula(texto)
        alienacao = next(ato for ato in resultado["atos"] if ato["codigo"] == "R.04")

        self.assertEqual("ATIVO", alienacao["status"])
        self.assertEqual("POSITIVA PARA ÔNUS", resultado["resultado"])


if __name__ == "__main__":
    unittest.main()
