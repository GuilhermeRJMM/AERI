import unittest
from types import SimpleNamespace

from backend.app.analise.pipeline_eventos import executar_pipeline_paralelo


class PipelineEventosTests(unittest.TestCase):
    def test_pipeline_paralelo_nao_altera_resultado_oficial(self):
        atos = [
            SimpleNamespace(codigo="R.1", descricao="VENDA E COMPRA", categoria="IGNORAR",
                            tipo_onus=None, status="ATIVO", cancelado_por=None, cancela_atos=[]),
            SimpleNamespace(codigo="R.2", descricao="ALIENAÇÃO FIDUCIÁRIA", categoria="ÔNUS",
                            tipo_onus="ALIENAÇÃO FIDUCIÁRIA", status="CANCELADO",
                            cancelado_por="AV.3", cancela_atos=[]),
            SimpleNamespace(codigo="AV.3", descricao="CANCELAMENTO DO R.2", categoria="CANCELAMENTO",
                            tipo_onus=None, status="ATIVO", cancelado_por=None, cancela_atos=["R.2"]),
        ]
        retorno = executar_pipeline_paralelo(
            atos,
            [{"nome": "ANA", "proporcao": "100%"}],
            {"tipo": "URBANO", "cadastros": []},
        )
        self.assertEqual(retorno["modo"], "PARALELO")
        self.assertFalse(retorno["altera_resultado_oficial"])
        self.assertEqual(retorno["eventos"], 3)
        self.assertEqual(retorno["alertas"], [])

    def test_detecta_total_de_titularidade_incoerente(self):
        retorno = executar_pipeline_paralelo(
            [],
            [{"nome": "ANA", "proporcao": "60%"}, {"nome": "BIA", "proporcao": "30%"}],
            {"tipo": "URBANO", "cadastros": []},
        )
        self.assertEqual(retorno["alertas"][0]["regra"], "TITULARIDADE_TOTAL_DIVERGENTE")


if __name__ == "__main__":
    unittest.main()
