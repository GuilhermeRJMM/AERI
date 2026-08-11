import os
import json
import unittest
from unittest.mock import patch

from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.auditoria_integrada import (
    _texto_minimizado,
    complemento_configurado,
    construir_resumo_auditoria,
    executar_revisao_complementar,
    limite_complementar_diario,
)


class _RespostaGatewayFalsa:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({
            "choices": [{"message": {"content": json.dumps({
                "conclusao": "INCONCLUSIVO",
                "confianca": "BAIXA",
                "dominios": ["CADEIA"],
                "hipoteses": ["Conferir o ato indicado."],
                "atos_relevantes": ["R.01"],
            })}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30},
        }).encode("utf-8")


class TesteAuditoriaIntegrada(unittest.TestCase):
    def test_usa_resultado_existente_e_nao_persiste_texto(self):
        texto = (
            "MATRÍCULA 100. IMÓVEL: Lote 1, Quadra 2, com área de 300,00 m². "
            "PROPRIETÁRIO: JOÃO DA SILVA, CPF 123.456.789-01."
        )
        resultado = analisar_matricula(texto, numero_matricula="100")
        resumo = construir_resumo_auditoria(100, texto, resultado)

        self.assertEqual(100, resumo["numero"])
        self.assertEqual(resultado["resultado_hash"], resumo["resultado_hash"])
        self.assertEqual(64, len(resumo["auditoria_hash"]))
        self.assertNotIn("texto", resumo)
        self.assertNotIn("JOÃO DA SILVA", str(resumo))

    def test_minimiza_documentos_antes_da_revisao_complementar(self):
        texto = "CPF 123.456.789-01 e CNPJ 12.345.678/0001-90"
        minimizado = _texto_minimizado(texto)

        self.assertIn("[CPF]", minimizado)
        self.assertIn("[CNPJ]", minimizado)
        self.assertNotIn("123.456.789-01", minimizado)
        self.assertNotIn("12.345.678/0001-90", minimizado)

    def test_revisao_complementar_fica_desativada_sem_limite_explicito(self):
        with patch.dict(os.environ, {
            "AI_GATEWAY_API_KEY": "chave-de-teste",
            "AERI_REVISAO_COMPLEMENTAR_LIMITE_DIA": "0",
        }, clear=False):
            self.assertEqual(0, limite_complementar_diario())
            self.assertFalse(complemento_configurado())

    def test_limite_diario_e_protegido_contra_valores_excessivos(self):
        with patch.dict(os.environ, {"AERI_REVISAO_COMPLEMENTAR_LIMITE_DIA": "9999"}):
            self.assertEqual(500, limite_complementar_diario())

    def test_revisao_complementar_usa_contrato_estruturado_e_mascara_documento(self):
        capturado = {}

        def responder(requisicao, timeout):
            capturado["corpo"] = requisicao.data.decode("utf-8")
            capturado["timeout"] = timeout
            return _RespostaGatewayFalsa()

        with patch.dict(os.environ, {
            "AI_GATEWAY_API_KEY": "chave-de-teste",
            "AERI_REVISAO_COMPLEMENTAR_LIMITE_DIA": "1",
        }), patch("backend.app.servicos.auditoria_integrada.urlopen", side_effect=responder):
            retorno = executar_revisao_complementar(
                "R.01. CPF 123.456.789-01. Compra e venda.",
                {"alertas": ["ULTIMA_TRANSFERENCIA_INTEGRAL_DIVERGENTE"]},
            )

        self.assertNotIn("123.456.789-01", capturado["corpo"])
        self.assertIn("[CPF]", capturado["corpo"])
        self.assertIn("json_schema", capturado["corpo"])
        self.assertEqual("INCONCLUSIVO", retorno["diagnostico"]["conclusao"])
        self.assertEqual(120, retorno["unidades_entrada"])


if __name__ == "__main__":
    unittest.main()
