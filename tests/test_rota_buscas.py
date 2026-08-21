import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.rotas import buscas, buscas_indexacao


class _CursorFalso:
    def __init__(self, linhas=None):
        self.linhas = linhas or []
        self.comandos = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, comando, parametros=()):
        self.comandos.append((comando, parametros))

    def fetchall(self):
        return self.linhas

    def fetchone(self):
        return {"total": 0}


class _ConexaoFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass


class _ClienteTri7Falso:
    def buscar_texto_matricula(self, numero):
        if int(numero) == 2:
            raise buscas.MatriculaTri7NaoEncontrada("ausente")
        return {"texto": f"MATRÍCULA {numero}. IMÓVEL: Lote. PROPRIETÁRIO: JOÃO."}


class TesteRotaBuscas(unittest.TestCase):
    def setUp(self):
        self.ambiente = patch.dict(os.environ, {"AERI_BUSCAS_HMAC_KEY": "segredo-de-teste-com-mais-de-16"})
        self.ambiente.start()

    def tearDown(self):
        self.ambiente.stop()

    def test_lote_preserva_ordem_e_trata_matricula_ausente(self):
        # O mock vai no módulo onde o nome é resolvido: _consultar_lote mora
        # em buscas_indexacao e busca ali o cliente da Tri7.
        with patch.object(
            buscas_indexacao, "cliente_tri7", return_value=_ClienteTri7Falso()
        ), patch.object(buscas._LimitadorTaxa, "aguardar", return_value=None):
            resultados, falha = buscas._consultar_lote([1, 2, 3])

        self.assertIsNone(falha)
        self.assertEqual([1, 2, 3], [item["numero"] for item in resultados])
        self.assertEqual(["OK", "NAO_ENCONTRADA", "OK"], [item["status"] for item in resultados])

    def test_nome_com_numero_continua_sendo_pesquisado_como_nome(self):
        cursor = _CursorFalso()
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.pesquisar_titularidade("FAZENDA 3 IRMÃOS", 100, "usuario", 1)

        self.assertEqual("NOME", resposta["tipoBusca"])
        self.assertIn("%FAZENDA 3 IRMAOS%", cursor.comandos[0][1])
        self.assertNotIn("m.situacao='ATIVA'", cursor.comandos[0][0])

    def test_busca_pagina_resultados_e_informa_total(self):
        cursor = _CursorFalso([{
            "numero": 8, "situacao": "ATIVA", "confianca_matricula": "ALTA",
            "consultado_em": datetime(2026, 8, 16, tzinfo=timezone.utc),
            "nome": "MUNICÍPIO DE MORRINHOS", "documento_mascarado": "",
            "tipo_documento": "", "proporcao": "100%", "origem": "R.1",
            "confianca": "MEDIA", "correspondencia": "NOME_EXATO",
        }])
        cursor.fetchone = lambda: {"total": 58}
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.pesquisar_titularidade(
                "Municipio de Morrinhos", 50, "usuario", 2
            )

        self.assertEqual(58, resposta["total"])
        self.assertEqual(2, resposta["pagina"])
        self.assertEqual(2, resposta["totalPaginas"])
        self.assertEqual(1, resposta["quantidade"])
        self.assertEqual((50, 50), cursor.comandos[-1][1][-2:])

    def test_exportacao_declaratoria_exige_nome_exato_em_consulta_unica(self):
        cursor = _CursorFalso([{
            "numero": 8, "situacao": "ATIVA",
            "consultado_em": datetime(2026, 8, 16, tzinfo=timezone.utc),
            "nome": "MUNICÍPIO DE MORRINHOS", "documento_mascarado": "",
            "tipo_documento": "", "proporcao": "100%", "origem": "R.1",
            "confianca": "ALTA",
        }])
        cursor.fetchone = lambda: {"total": 1}
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.exportar_pesquisa_titularidade(
                "Município de Morrinhos", "usuario"
            )

        self.assertEqual("NOME_EXATO", resposta["tipoBusca"])
        self.assertEqual(1, len(resposta["itens"]))
        self.assertNotIn("LIKE", cursor.comandos[-1][0])
        self.assertEqual(("MUNICIPIO DE MORRINHOS",), cursor.comandos[-1][1])

    def test_cpf_incompleto_e_recusado(self):
        with self.assertRaises(HTTPException) as contexto:
            buscas.pesquisar_titularidade("123.456", 100, "usuario", 1)
        self.assertEqual(422, contexto.exception.status_code)

    def test_documento_exato_usa_hash_e_nao_envia_cpf_ao_banco(self):
        cursor = _CursorFalso()
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.pesquisar_titularidade("123.456.789-01", 100, "usuario", 1)

        parametros = cursor.comandos[-1][1]
        self.assertEqual("DOCUMENTO_EXATO", resposta["tipoBusca"])
        self.assertNotIn("12345678901", parametros)
        self.assertTrue(any(isinstance(item, str) and len(item) == 64 for item in parametros))

    def test_documento_fica_bloqueado_durante_migracao_dos_hashes(self):
        cursor = _CursorFalso()
        cursor.fetchone = lambda: {"total": 3}
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            with self.assertRaises(HTTPException) as contexto:
                buscas.pesquisar_titularidade("123.456.789-01", 100, "usuario", 1)

        self.assertEqual(503, contexto.exception.status_code)
        self.assertIn("reindexados", contexto.exception.detail)

    def test_lista_pendencias_sem_expor_texto_registral(self):
        cursor = _CursorFalso([{
            "matricula_numero": 123,
            "estado": "REVISAR",
            "prioridade": "P0-CRITICA",
            "confianca_onus": "ALTA",
            "confianca_cadeia": "BAIXA",
            "confianca_imovel": "MEDIA",
            "alertas": ["CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA"],
            "complemento_status": "DESATIVADA",
            "complemento_diagnostico": None,
            "analisado_em": datetime(2026, 8, 11, tzinfo=timezone.utc),
        }])
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)):
            resposta = buscas.listar_pendencias_auditoria(100, "usuario")

        self.assertEqual(123, resposta[0]["matricula"])
        self.assertEqual("P0-CRITICA", resposta[0]["prioridade"])
        self.assertNotIn("texto", resposta[0])

    def test_diagnostico_mascara_documentos_e_nao_persiste_texto(self):
        texto = (
            "MATRÍCULA 123. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa, CPF 123.456.789-01. "
            "R.01-123 - HIPOTECA. Devedor CPF 123.456.789-01; credor CNPJ "
            "12.345.678/0001-90. O imóvel foi dado em hipoteca."
        )
        request = SimpleNamespace()
        with patch.object(
            buscas, "_consultar_lote", return_value=([{"numero": 123, "status": "OK", "texto": texto}], None)
        ), patch.object(buscas, "registrar_auditoria"):
            resposta = buscas.diagnosticar_pendencia_auditoria(123, request, "auditor")

        serializado = str(resposta)
        self.assertNotIn("123.456.789-01", serializado)
        self.assertNotIn("12.345.678/0001-90", serializado)
        self.assertEqual("[DOCUMENTO]", resposta["proprietarios"][0]["documento"])
        self.assertTrue(resposta["meta"]["documentosMascarados"])
        self.assertFalse(resposta["meta"]["textoPersistido"])

    def test_diagnostico_detalhado_expoe_somente_nomes_e_percentuais_por_ato(self):
        texto = (
            "MATRÍCULA 123. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Inicial.\n\n"
            "R.01-123 - Morrinhos, 1 de janeiro de 2020. COMPRA E VENDA. O "
            "imóvel foi adquirido por Pessoa Atual, CPF 123.456.789-01, por "
            "compra feita a Pessoa Inicial.\n---"
        )
        request = SimpleNamespace()
        with patch.object(
            buscas, "_consultar_lote",
            return_value=([{"numero": 123, "status": "OK", "texto": texto}], None),
        ), patch.object(buscas, "registrar_auditoria"):
            resposta = buscas.diagnosticar_pendencia_auditoria(
                123, request, "auditor", detalhar=True
            )

        self.assertEqual("R.01", resposta["cadeiaPassos"][0]["codigo"])
        self.assertNotIn("documento", resposta["cadeiaPassos"][0]["proprietarios"][0])
        self.assertNotIn("123.456.789-01", str(resposta["cadeiaPassos"]))

    def test_reprocessamento_de_pendencias_avanca_cursor_e_resume_estados(self):
        cursor = _CursorFalso([
            {"matricula_numero": 40},
            {"matricula_numero": 41},
        ])
        cursor.fetchone = lambda: {"id": 1}
        resultados = [
            {"numero": 40, "status": "OK", "texto": "matricula 40"},
            {"numero": 41, "status": "OK", "texto": "matricula 41"},
        ]
        retornos_indice = [
            ({}, False, True, {"estado": "VALIDADA_AUTOMATICAMENTE"}, False),
            ({}, False, True, {"estado": "REVISAR"}, False),
        ]
        request = SimpleNamespace()
        with patch.object(buscas, "conectar", return_value=_ConexaoFalsa(cursor)), patch.object(
            buscas, "validar_configuracao_buscas"
        ), patch.object(buscas, "_consultar_lote", return_value=(resultados, None)), patch.object(
            buscas, "_salvar_indice", side_effect=retornos_indice
        ), patch.object(buscas, "_estado_json", return_value={"auditoriaRevisar": 1}), patch.object(
            buscas, "registrar_auditoria_cursor"
        ):
            resposta = buscas.reprocessar_pendencias_auditoria(
                {"apos": 0, "tamanho": 30}, request, "auditor"
            )

        self.assertEqual(2, resposta["processados"])
        self.assertEqual(1, resposta["validadas"])
        self.assertEqual(1, resposta["aindaPendentes"])
        self.assertEqual(41, resposta["proximo"])
        self.assertFalse(resposta["concluido"])


if __name__ == "__main__":
    unittest.main()
