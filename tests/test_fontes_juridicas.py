import json
import os
import unittest
from unittest.mock import patch

from backend.app.servicos.fontes_juridicas import (
    _matricula_minimizada,
    agente_juridico_configurado,
    executar_agente_juridico,
    inferir_metadados,
    limite_agente_juridico_diario,
    segmentar_paginas,
)


class _RespostaGateway:
    def __init__(self, parecer):
        self.parecer = parecer

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({
            "choices": [{"message": {"content": json.dumps(self.parecer)}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 180},
        }).encode("utf-8")


class TesteFontesJuridicas(unittest.TestCase):
    def test_infere_esferas_e_referencia_pelo_nome(self):
        municipal = inferir_metadados("Lei Municipal n.º 2.050 de 2004.pdf")
        cnj = inferir_metadados("Provimento 149-2023 - CNJ.pdf")

        self.assertEqual("MUNICIPAL_MORRINHOS", municipal["jurisdicao"])
        self.assertIn("Lei Municipal", municipal["referencia_normativa"])
        self.assertEqual("NACIONAL", cnj["jurisdicao"])
        self.assertEqual("Conselho Nacional de Justiça", cnj["autoridade"])

    def test_segmenta_preservando_pagina_e_artigo(self):
        paginas = [
            (1, "Art. 1º Esta norma disciplina o registro. " * 8),
            (2, "Art. 2º A averbação observará os requisitos legais. " * 8),
        ]
        trechos = segmentar_paginas(paginas, limite=220)

        self.assertGreaterEqual(len(trechos), 2)
        self.assertEqual(1, trechos[0]["pagina_inicial"])
        self.assertTrue(any("Art. 2" in item["referencia"] for item in trechos))

    def test_doutrina_nao_recebe_classe_de_fonte_primaria(self):
        metadados = inferir_metadados("Codigo Civil Comentado - exemplo.pdf")
        self.assertEqual("DOUTRINA", metadados["classe_fonte"])

    def test_mascara_documentos_antes_de_enviar(self):
        texto = _matricula_minimizada(
            "CPF 123.456.789-01, CNPJ 12.345.678/0001-90 e e-mail pessoa@exemplo.com"
        )
        self.assertNotIn("123.456.789-01", texto)
        self.assertNotIn("12.345.678/0001-90", texto)
        self.assertNotIn("pessoa@exemplo.com", texto)
        self.assertIn("[CPF]", texto)

    def test_agente_exige_configuracao_e_limita_cota(self):
        with patch.dict(os.environ, {
            "AI_GATEWAY_API_KEY": "chave",
            "AERI_AGENTE_JURIDICO_LIMITE_DIA": "9999",
        }, clear=False):
            self.assertTrue(agente_juridico_configurado())
            self.assertEqual(200, limite_agente_juridico_diario())

    def test_agente_cita_apenas_fontes_fornecidas(self):
        parecer = {
            "conclusao": "ATENCAO",
            "confianca": "MEDIA",
            "resumo": "Há um ponto que exige conferência.",
            "analises": [
                {
                    "dominio": dominio, "status": "ATENCAO",
                    "resultado_identificado": "Resultado do domínio.",
                    "fundamentacao": "Fundamentação jurídica do domínio.",
                    "atos_envolvidos": ["AV.2"], "citacoes": ["F1"],
                }
                for dominio in ("ONUS", "IMOVEL", "PROPRIETARIOS")
            ],
            "acoes_recomendadas": ["Conferir o ato na matrícula."],
        }
        fonte = {
            "texto": "Art. 1º A averbação da constrição será lançada na matrícula.",
            "titulo": "Norma de teste",
            "referencia": "Art. 1º",
            "referencia_normativa": "",
            "pagina_inicial": 1,
            "pagina_final": 1,
            "jurisdicao": "NACIONAL",
            "autoridade": "CNJ",
            "url_oficial": "https://atos.cnj.jus.br/teste",
            "sha256": "a" * 64,
        }
        capturado = {}

        def responder(requisicao, timeout):
            capturado["corpo"] = requisicao.data.decode("utf-8")
            capturado["timeout"] = timeout
            return _RespostaGateway(parecer)

        with patch.dict(os.environ, {
            "AI_GATEWAY_API_KEY": "chave",
            "AERI_AGENTE_JURIDICO_LIMITE_DIA": "1",
        }), patch("backend.app.servicos.fontes_juridicas.urlopen", side_effect=responder):
            revisao = executar_agente_juridico(
                "AV.2. Penhora. CPF 123.456.789-01.",
                {"resultado": "POSITIVA PARA ÔNUS", "atos": [], "imovel": {}},
                [fonte],
            )

        self.assertNotIn("123.456.789-01", capturado["corpo"])
        self.assertIn("feature:agente-juridico", capturado["corpo"])
        self.assertEqual("ATENCAO", revisao["parecer"]["conclusao"])
        self.assertEqual("F1", revisao["fontes"][0]["id"])
        self.assertEqual(55, capturado["timeout"])

    def test_agente_rejeita_citacao_inventada(self):
        parecer = {
            "conclusao": "ATENCAO",
            "confianca": "ALTA",
            "resumo": "Divergência.",
            "analises": [
                {
                    "dominio": dominio, "status": "ATENCAO",
                    "resultado_identificado": "Resultado.",
                    "fundamentacao": "Conclusão com fonte.",
                    "atos_envolvidos": ["R.1"],
                    "citacoes": ["F99" if dominio == "PROPRIETARIOS" else "F1"],
                }
                for dominio in ("ONUS", "IMOVEL", "PROPRIETARIOS")
            ],
            "acoes_recomendadas": [],
        }
        fonte = {
            "texto": "Art. 1º Texto suficiente para formar um trecho jurídico.",
            "titulo": "Fonte", "referencia": "Art. 1º", "referencia_normativa": "",
            "pagina_inicial": 1, "pagina_final": 1, "jurisdicao": "FEDERAL",
            "autoridade": "União", "url_oficial": "", "sha256": "b" * 64,
        }
        with patch.dict(os.environ, {
            "AI_GATEWAY_API_KEY": "chave", "AERI_AGENTE_JURIDICO_LIMITE_DIA": "1",
        }), patch(
            "backend.app.servicos.fontes_juridicas.urlopen",
            return_value=_RespostaGateway(parecer),
        ):
            with self.assertRaisesRegex(RuntimeError, "fonte ou domínio inválido"):
                executar_agente_juridico("Matrícula", {"atos": [], "imovel": {}}, [fonte])


if __name__ == "__main__":
    unittest.main()
