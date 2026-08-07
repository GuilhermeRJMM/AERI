import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from backend.app.rotas.livro_protocolos import analisar_livro_protocolos
from backend.app.servicos.tri7 import ErroTri7, ProtocoloTri7NaoEncontrado


def _requisicao_pdf(pdf_bytes: bytes, tamanho: int | None = None) -> Mock:
    requisicao = Mock()
    requisicao.headers = {"content-length": str(tamanho if tamanho is not None else len(pdf_bytes))}
    requisicao.body = AsyncMock(return_value=pdf_bytes)
    return requisicao


def _rodar(coro):
    return asyncio.run(coro)


class TesteAnalisarLivroProtocolos(unittest.TestCase):
    @patch("backend.app.rotas.livro_protocolos.registrar_auditoria")
    def test_rejeita_arquivo_que_nao_comeca_com_assinatura_pdf(self, _auditoria):
        requisicao = _requisicao_pdf(b"nao e um pdf")
        with self.assertRaises(HTTPException) as contexto:
            _rodar(analisar_livro_protocolos(requisicao, usuario="operador"))
        self.assertEqual(contexto.exception.status_code, 422)

    @patch("backend.app.rotas.livro_protocolos.registrar_auditoria")
    def test_content_length_acima_do_limite_e_rejeitado_sem_ler_corpo(self, _auditoria):
        requisicao = _requisicao_pdf(b"%PDF-1.4\n%%EOF", tamanho=16_000_000)
        with self.assertRaises(HTTPException) as contexto:
            _rodar(analisar_livro_protocolos(requisicao, usuario="operador"))
        self.assertEqual(contexto.exception.status_code, 413)
        requisicao.body.assert_not_called()

    @patch("backend.app.rotas.livro_protocolos.registrar_auditoria")
    @patch("backend.app.rotas.livro_protocolos.cliente_tri7")
    @patch("backend.app.rotas.livro_protocolos.conferir_protocolo")
    @patch("backend.app.rotas.livro_protocolos.extrair_protocolos_pdf")
    def test_so_consulta_a_tri7_para_itens_registrados(
        self, extrair_mock, conferir_mock, obter_cliente, _auditoria,
    ):
        extrair_mock.return_value = [
            {"numero": "185200", "numeroFormatado": "185.200", "status": "PRENOTADO", "data": "2026-08-05"},
            {"numero": "184455", "numeroFormatado": "184.455", "status": "SEM_EFEITO", "data": "2026-06-26"},
            {"numero": "185110", "numeroFormatado": "185.110", "status": "REGISTRADO", "data": "2026-07-31"},
        ]
        obter_cliente.return_value.buscar_protocolo_completo.return_value = {
            "protocolo": {"protocolo_numero": 185110}, "itens_do_pedido": [],
        }
        conferir_mock.return_value = []

        requisicao = _requisicao_pdf(b"%PDF-1.4\n%%EOF")
        resultado = _rodar(analisar_livro_protocolos(requisicao, usuario="operador"))

        obter_cliente.return_value.buscar_protocolo_completo.assert_called_once_with("185110")
        self.assertEqual(resultado["resumo"]["total"], 3)
        self.assertEqual(resultado["resumo"]["registrados"], 1)
        self.assertEqual(resultado["resumo"]["conferidos"], 1)
        registrado = next(p for p in resultado["protocolos"] if p["numero"] == "185110")
        self.assertTrue(registrado["conferido"])
        prenotado = next(p for p in resultado["protocolos"] if p["numero"] == "185200")
        self.assertFalse(prenotado["conferido"])
        self.assertIsNone(prenotado["erro"])

    @patch("backend.app.rotas.livro_protocolos.registrar_auditoria")
    @patch("backend.app.rotas.livro_protocolos.cliente_tri7")
    @patch("backend.app.rotas.livro_protocolos.extrair_protocolos_pdf")
    def test_falha_na_tri7_nao_interrompe_os_demais_protocolos(
        self, extrair_mock, obter_cliente, _auditoria,
    ):
        extrair_mock.return_value = [
            {"numero": "185110", "numeroFormatado": "185.110", "status": "REGISTRADO", "data": "2026-07-31"},
            {"numero": "185120", "numeroFormatado": "185.120", "status": "REGISTRADO", "data": "2026-07-31"},
        ]
        obter_cliente.return_value.buscar_protocolo_completo.side_effect = [
            ProtocoloTri7NaoEncontrado("Protocolo 185110 não encontrado na Tri7."),
            {"protocolo": {"protocolo_numero": 185120}, "itens_do_pedido": []},
        ]

        with patch("backend.app.rotas.livro_protocolos.conferir_protocolo", return_value=[]):
            requisicao = _requisicao_pdf(b"%PDF-1.4\n%%EOF")
            resultado = _rodar(analisar_livro_protocolos(requisicao, usuario="operador"))

        self.assertEqual(resultado["resumo"]["falhasConsulta"], 1)
        self.assertEqual(resultado["resumo"]["conferidos"], 1)
        item_com_falha = next(p for p in resultado["protocolos"] if p["numero"] == "185110")
        self.assertIsNotNone(item_com_falha["erro"])
        self.assertFalse(item_com_falha["conferido"])

    @patch("backend.app.rotas.livro_protocolos.registrar_auditoria")
    @patch("backend.app.rotas.livro_protocolos.extrair_protocolos_pdf")
    def test_pdf_sem_protocolos_reconhecidos_vira_422(self, extrair_mock, _auditoria):
        extrair_mock.side_effect = ValueError("Nenhum protocolo foi identificado neste PDF.")

        requisicao = _requisicao_pdf(b"%PDF-1.4\n%%EOF")
        with self.assertRaises(HTTPException) as contexto:
            _rodar(analisar_livro_protocolos(requisicao, usuario="operador"))
        self.assertEqual(contexto.exception.status_code, 422)

    @patch("backend.app.rotas.livro_protocolos.registrar_auditoria")
    @patch("backend.app.rotas.livro_protocolos.cliente_tri7")
    @patch("backend.app.rotas.livro_protocolos.conferir_protocolo")
    @patch("backend.app.rotas.livro_protocolos.extrair_protocolos_pdf")
    def test_erro_generico_da_tri7_fica_registrado_no_item_sem_derrubar_a_analise(
        self, extrair_mock, conferir_mock, obter_cliente, _auditoria,
    ):
        extrair_mock.return_value = [
            {"numero": "185110", "numeroFormatado": "185.110", "status": "REGISTRADO", "data": "2026-07-31"},
        ]
        obter_cliente.return_value.buscar_protocolo_completo.side_effect = ErroTri7("A Tri7 está indisponível.")

        requisicao = _requisicao_pdf(b"%PDF-1.4\n%%EOF")
        resultado = _rodar(analisar_livro_protocolos(requisicao, usuario="operador"))

        conferir_mock.assert_not_called()
        self.assertEqual(resultado["resumo"]["falhasConsulta"], 1)
        self.assertEqual(resultado["protocolos"][0]["erro"], "A Tri7 está indisponível.")


if __name__ == "__main__":
    unittest.main()
