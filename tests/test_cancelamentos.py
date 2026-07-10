import unittest
from types import SimpleNamespace

from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.regras import REGRAS, classificar


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


if __name__ == "__main__":
    unittest.main()
