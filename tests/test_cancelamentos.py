import unittest
from types import SimpleNamespace

from backend.app.cancelamentos import aplicar_cancelamentos
from backend.app.regras import classificar


def ato(codigo, descricao):
    categoria, impacta = classificar(descricao)
    return SimpleNamespace(
        codigo=codigo,
        descricao=descricao,
        categoria=categoria,
        impacta_resultado=impacta,
        status="ATIVO",
        cancelado_por=None,
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


class TesteCancelamentos(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
