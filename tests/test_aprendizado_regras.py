import unittest

from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.aprendizado_regras import (
    normalizar_expressao,
    validar_sugestao_aprendizado,
)


class TesteAprendizadoRegras(unittest.TestCase):
    def test_normaliza_expressao_para_busca_deterministica(self):
        self.assertEqual(normalizar_expressao("  Alienação   Fiduciária  "), "ALIENACAO FIDUCIARIA")

    def test_rejeita_termo_com_numero_longo(self):
        with self.assertRaises(ValueError):
            validar_sugestao_aprendizado({
                "expressao": "CPF 123.456.789-10",
                "categoria": "PUBLICIDADE",
            })

    def test_mascara_documento_na_justificativa(self):
        sugestao = validar_sugestao_aprendizado({
            "expressao": "blindagem patrimonial",
            "categoria": "ÔNUS",
            "tipo_onus": "garantia atípica",
            "justificativa": "Conferido no CPF 123.456.789-10.",
        })
        self.assertIn("[CPF]", sugestao["justificativa"])
        self.assertNotIn("123.456.789-10", sugestao["justificativa"])

    def test_regra_aprovada_altera_resultado_sem_ia(self):
        texto = """
        MATRÍCULA 100
        AV.01- BLINDAGEM PATRIMONIAL. O imóvel permanece vinculado ao termo.
        """
        regras = [{
            "expressao_normalizada": "BLINDAGEM PATRIMONIAL",
            "categoria": "ÔNUS",
            "impacta_resultado": True,
            "tipo_onus": "BLINDAGEM PATRIMONIAL",
        }]
        resultado = analisar_matricula(texto, regras_aprendidas=regras)
        self.assertEqual(resultado["resultado"], "POSITIVA PARA ÔNUS")
        self.assertEqual(resultado["atos"][0]["tipo_onus"], "BLINDAGEM PATRIMONIAL")


if __name__ == "__main__":
    unittest.main()
