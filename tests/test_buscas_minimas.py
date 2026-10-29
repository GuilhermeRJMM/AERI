import inspect
import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from backend.app.servicos.busca_textual import documento_da_consulta, escapar_like, nomes_equivalentes
from backend.app.servicos.custas import _identidade_compativel
from backend.app.rotas.registros_auxiliares import pesquisar_registros_auxiliares, diagnostico_buscas
from backend.app.servicos.diagnostico_buscas import diagnosticar_cursor, medir_nome_cursor

os.environ.setdefault("AERI_BUSCAS_HMAC_KEY", "segredo-sintetico-melhoria-buscas")


class IdentidadeTests(unittest.TestCase):
    def test_documentos_nao_sao_extraidos_de_nome_de_empresa(self):
        self.assertIsNone(documento_da_consulta("LS3 Saran"))
        self.assertIsNone(documento_da_consulta("Empresa 12345678901"))
        self.assertEqual("12345678901", documento_da_consulta("123.456.789-01"))
        for termo in ["1234", "123456789012345", "123456789012345678"]:
            with self.subTest(termo=termo), self.assertRaises(ValueError):
                documento_da_consulta(termo)

    def test_nome_equivalente_nao_aceita_sobrenome_faltante(self):
        self.assertTrue(nomes_equivalentes("João da Silva", "SILVA JOAO"))
        self.assertFalse(nomes_equivalentes("JOAO SILVA", "JOAO SILVA NETO"))
        self.assertFalse(nomes_equivalentes("JOAO", "JOAO SILVA"))
        self.assertFalse(nomes_equivalentes("", ""))

    def test_curingas_sao_literais(self):
        self.assertEqual(r"JOAO\%\_\\", escapar_like("JOAO%_\\"))

    def test_custas_documento_contraditorio_nao_confirma_nome(self):
        registro = {"pessoas": [{"nome": "JOAO SILVA", "documento_hash": "outro"}]}
        self.assertFalse(_identidade_compativel(
            registro, {"nome": "JOAO SILVA", "documento": "12345678901"}, "esperado"))
        self.assertFalse(_identidade_compativel(
            {"pessoas": [{"nome": "JOAO SILVA NETO"}]}, {"nome": "JOAO SILVA"}, ""))

    @patch("backend.app.rotas.registros_auxiliares.conectar")
    def test_busca_documental_nao_tem_alternativa_por_nome(self, conectar):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conectar.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        pesquisar_registros_auxiliares(busca="123.456.789-01", limite=100, _usuario="TESTE")
        sql, params = cursor.execute.call_args.args
        self.assertIn("documentos_hash ? %s", sql)
        self.assertNotIn("nomes_busca LIKE", sql)
        self.assertNotIn("12345678901", str(params))


class DiagnosticoTests(unittest.TestCase):
    def test_diagnostico_so_expoe_metricas_e_detecta_indice_invalido(self):
        cursor = MagicMock()
        agora = datetime.now(timezone.utc)
        cursor.fetchone.side_effect = [
            {"extname": "pg_trgm"},
            {"total": 10, "documentos_pendentes": 2, "consulta_mais_antiga": agora,
             "consulta_mais_recente": agora},
            {"erros": 0, "fila_total": 1, "fila_vencida": 1, "ausencias": 2},
            {"ultima_sondagem_novos_em": agora, "ultima_varredura_lacunas_em": None},
        ]
        cursor.fetchall.return_value = [
            {"nome": "idx_reg_aux_nomes_trgm", "valido": False, "pronto": True, "leituras": 0}]
        saida = diagnosticar_cursor(cursor)
        self.assertIn("idx_reg_aux_nomes_trgm", saida["indicesAusentesOuInvalidos"])
        self.assertTrue(saida["pgTrgmAtivo"])
        self.assertEqual(saida["cobertura"]["documentos_pendentes"], 2)
        for chamada in cursor.execute.call_args_list:
            self.assertTrue(chamada.args[0].lstrip().upper().startswith("SELECT"))

    def test_medicao_nao_devolve_condicoes_com_nomes_ou_documentos(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"QUERY PLAN": [{
            "Planning Time": 1.1, "Execution Time": 2.2,
            "Plan": {"Node Type": "Bitmap Heap Scan", "Actual Rows": 2,
                     "Filter": "nome=SEGREDO", "Index Cond": "documento=SEGREDO",
                     "Plans": [{"Node Type": "Bitmap Index Scan", "Index Name": "idx_teste"}]},
        }]}
        dados = medir_nome_cursor(cursor, "SEGREDO")
        self.assertNotIn("SEGREDO", json.dumps(dados))
        self.assertEqual(dados["execucaoMs"], 2.2)
        self.assertEqual(len(dados["operacoes"]), 2)

    def test_rota_restrita_a_administrativos(self):
        verificar = inspect.signature(diagnostico_buscas).parameters["_usuario"].default.dependency
        request = SimpleNamespace(state=SimpleNamespace(
            sessao={"perfil": "USUARIO", "deve_trocar_senha": False}))
        with self.assertRaises(HTTPException) as erro:
            verificar(request, "TESTE")
        self.assertEqual(erro.exception.status_code, 403)
        request.state.sessao["perfil"] = "ADMIN"
        self.assertEqual(verificar(request, "TESTE"), "TESTE")


if __name__ == "__main__":
    unittest.main()
