import os
import unittest
from unittest.mock import patch

from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.buscas import (
    construir_indice_matricula,
    hash_documento,
    mascarar_documento,
    normalizar_documento,
    normalizar_nome,
    validar_configuracao_buscas,
)


class TesteServicoBuscas(unittest.TestCase):
    def setUp(self):
        self.ambiente = patch.dict(os.environ, {"AERI_BUSCAS_HMAC_KEY": "segredo-de-teste-com-mais-de-16"})
        self.ambiente.start()

    def tearDown(self):
        self.ambiente.stop()

    def test_normaliza_nome_e_documento(self):
        self.assertEqual("JOAO D AVILA", normalizar_nome("  João D'Ávila "))
        self.assertEqual("12345678901", normalizar_documento("123.456.789-01"))

    def test_documento_e_indexado_com_hmac_e_exibido_mascarado(self):
        protegido = hash_documento("123.456.789-01")
        self.assertEqual(64, len(protegido))
        self.assertNotIn("12345678901", protegido)
        self.assertEqual(protegido, hash_documento("12345678901"))
        self.assertEqual("***.***.789-01", mascarar_documento("123.456.789-01"))

    def test_matricula_ativa_indexa_apenas_proprietarios_atuais(self):
        texto = (
            "MATRÍCULA 100. IMÓVEL: Lote 1. "
            "PROPRIETÁRIO: JOÃO DA SILVA, CPF 123.456.789-01, casado com MARIA DA SILVA."
        )
        resultado = analisar_matricula(texto, numero_matricula="100")
        indice = construir_indice_matricula(100, texto, resultado)

        self.assertEqual("ATIVA", indice["situacao"])
        self.assertEqual(1, len(indice["proprietarios"]))
        self.assertEqual("JOÃO DA SILVA", indice["proprietarios"][0]["nome"])
        self.assertNotIn("MARIA DA SILVA", [item["nome"] for item in indice["proprietarios"]])
        self.assertEqual(64, len(indice["texto_hash"]))
        self.assertNotIn("texto", indice)

    def test_matricula_encerrada_mantem_proprietarios_pesquisaveis(self):
        resultado = {
            "proprietarios_atuais": [{"nome": "ANA LÚCIA", "cpf": "111.222.333-44", "proporcao": "100%"}],
            "imovel": {"situacao": {
                "status": "ENCERRADA", "origem": "AV.02",
                "matricula_sucessora": "200",
            }},
            "meta": {"versao": "2.0.0"},
            "resultado_hash": "a" * 64,
            "evidencias": {"proprietarios": [{"fonte": "R.01"}]},
        }
        indice = construir_indice_matricula(100, "texto encerrado", resultado)

        self.assertEqual("ENCERRADA", indice["situacao"])
        self.assertEqual(["200"], indice["matriculas_sucessoras"])
        self.assertEqual(1, len(indice["proprietarios"]))
        self.assertEqual("ANA LÚCIA", indice["proprietarios"][0]["nome"])
        self.assertEqual("***.***.333-44", indice["proprietarios"][0]["documento_mascarado"])

    def test_sem_segredo_recusa_indexar_documento(self):
        with patch.dict(os.environ, {"AERI_BUSCAS_HMAC_KEY": "", "CRON_SECRET": ""}):
            with self.assertRaisesRegex(RuntimeError, "AERI_BUSCAS_HMAC_KEY"):
                hash_documento("12345678901")

    def test_cron_secret_sozinho_nao_serve_mais_de_fallback(self):
        # Regressão: CRON_SECRET e AERI_BUSCAS_HMAC_KEY são segredos com
        # propósitos diferentes (autenticação do cron vs. hash irreversível
        # dos documentos indexados). Reaproveitar CRON_SECRET como fallback
        # fazia uma rotação dele (por qualquer motivo relacionado ao cron)
        # mudar silenciosamente o hash de todo documento já indexado.
        with patch.dict(os.environ, {"AERI_BUSCAS_HMAC_KEY": "", "CRON_SECRET": "segredo-do-cron-nao-relacionado"}):
            with self.assertRaisesRegex(RuntimeError, "AERI_BUSCAS_HMAC_KEY"):
                hash_documento("12345678901")

    def test_validacao_antecipa_ausencia_da_chave_do_indice(self):
        with patch.dict(os.environ, {"AERI_BUSCAS_HMAC_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "AERI_BUSCAS_HMAC_KEY"):
                validar_configuracao_buscas()


if __name__ == "__main__":
    unittest.main()
