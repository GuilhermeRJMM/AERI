import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from backend.app.rotas.incra import analisar_incra
from backend.app.servicos.tri7 import ErroTri7, ProtocoloTri7NaoEncontrado


def _requisicao_pdf(pdf_bytes: bytes, tamanho: int | None = None) -> Mock:
    requisicao = Mock()
    requisicao.headers = {"content-length": str(tamanho if tamanho is not None else len(pdf_bytes))}
    requisicao.body = AsyncMock(return_value=pdf_bytes)
    return requisicao


def _resultado_pdf() -> dict:
    return {
        "paginas": 1,
        "lancamentos": 3,
        "protocolos_unicos": 2,
        "itens": [
            {"protocolo": "185039", "ato": "Georreferenciamento", "status": "COMUNICAR",
             "motivo": "Alteração territorial", "ocorrencias": 1},
            {"protocolo": "185039", "ato": "Desmembramento", "status": "COMUNICAR",
             "motivo": "Desmembramento", "ocorrencias": 1},
            {"protocolo": "185999", "ato": "Averbação", "status": "REVISAR",
             "motivo": "Conferir", "ocorrencias": 1},
        ],
        "contagens": {"COMUNICAR": 2, "REVISAR": 1, "FORA_DAS_HIPOTESES": 0},
    }


class RotaIncraTests(unittest.TestCase):
    @patch("backend.app.rotas.incra.registrar_auditoria")
    def test_rejeita_arquivo_invalido(self, _auditoria):
        with self.assertRaises(HTTPException) as contexto:
            asyncio.run(analisar_incra(_requisicao_pdf(b"nao pdf"), usuario="operador"))
        self.assertEqual(contexto.exception.status_code, 422)

    @patch("backend.app.rotas.incra._LimitadorTaxaTri7.aguardar")
    @patch("backend.app.rotas.incra.registrar_auditoria")
    @patch("backend.app.rotas.incra.cliente_tri7")
    @patch("backend.app.rotas.incra.extrair_protocolos")
    def test_consulta_cada_protocolo_unico_e_enriquece_itens_repetidos(
        self, extrair_mock, obter_cliente, _auditoria, _aguardar,
    ):
        extrair_mock.return_value = _resultado_pdf()
        obter_cliente.return_value.buscar_protocolo_completo.side_effect = [
            {
                "protocolo": {"protocolo_numero": 185039},
                "andamentos": [{"andamento_tipo": "Finalizado Decurso de Prazo"}],
                "itens_do_pedido": [],
            },
            {
                "protocolo": {"protocolo_numero": 185999},
                "andamentos": [{"andamento_tipo": "Finalizado"}],
                "itens_do_pedido": [{
                    "dados_imovel": {"tipo_registro": "M", "numero_registro": 40001},
                    "atos_registrados": {"ato_tipo": "A", "ato_numero": 3},
                }],
            },
        ]
        obter_cliente.return_value.buscar_texto_matricula.return_value = {
            "numero_matricula": "40001",
            "texto": "AV.03-40.001. Protocolo n.º 185.999. Texto do ato.",
        }

        resultado = asyncio.run(analisar_incra(
            _requisicao_pdf(b"%PDF-1.4\n%%EOF"), usuario="operador",
        ))

        self.assertEqual(obter_cliente.return_value.buscar_protocolo_completo.call_count, 2)
        self.assertEqual(resultado["consultados_tri7"], 2)
        self.assertEqual(resultado["falhas_tri7"], 0)
        self.assertEqual(resultado["itens"][0]["situacaoTri7"], "CANCELADO_DECURSO_PRAZO")
        self.assertEqual(resultado["itens"][1]["situacaoTri7"], "CANCELADO_DECURSO_PRAZO")
        self.assertEqual(resultado["itens"][2]["matriculas"][0]["atos"], ["AV.3"])
        obter_cliente.return_value.buscar_texto_matricula.assert_not_called()

    @patch("backend.app.rotas.incra._LimitadorTaxaTri7.aguardar")
    @patch("backend.app.rotas.incra.registrar_auditoria")
    @patch("backend.app.rotas.incra.cliente_tri7")
    @patch("backend.app.rotas.incra.extrair_protocolos")
    def test_falhas_da_tri7_nao_apagam_resultado_do_relatorio(
        self, extrair_mock, obter_cliente, _auditoria, _aguardar,
    ):
        resultado_pdf = _resultado_pdf()
        resultado_pdf["itens"] = resultado_pdf["itens"][:2]
        resultado_pdf["protocolos_unicos"] = 1
        extrair_mock.return_value = resultado_pdf
        obter_cliente.return_value.buscar_protocolo_completo.side_effect = ErroTri7(
            "A Tri7 está indisponível."
        )

        resultado = asyncio.run(analisar_incra(
            _requisicao_pdf(b"%PDF-1.4\n%%EOF"), usuario="operador",
        ))

        self.assertEqual(len(resultado["itens"]), 2)
        self.assertEqual(resultado["falhas_tri7"], 1)
        self.assertEqual(resultado["itens"][0]["situacaoTri7"], "CONSULTA_INDISPONIVEL")

    @patch("backend.app.rotas.incra._LimitadorTaxaTri7.aguardar")
    @patch("backend.app.rotas.incra.registrar_auditoria")
    @patch("backend.app.rotas.incra.cliente_tri7")
    @patch("backend.app.rotas.incra.extrair_protocolos")
    def test_protocolo_ausente_fica_sinalizado(
        self, extrair_mock, obter_cliente, _auditoria, _aguardar,
    ):
        resultado_pdf = _resultado_pdf()
        resultado_pdf["itens"] = resultado_pdf["itens"][:1]
        resultado_pdf["protocolos_unicos"] = 1
        extrair_mock.return_value = resultado_pdf
        obter_cliente.return_value.buscar_protocolo_completo.side_effect = (
            ProtocoloTri7NaoEncontrado("Não encontrado")
        )

        resultado = asyncio.run(analisar_incra(
            _requisicao_pdf(b"%PDF-1.4\n%%EOF"), usuario="operador",
        ))

        self.assertEqual(resultado["itens"][0]["situacaoTri7"], "NAO_LOCALIZADO")
        self.assertEqual(resultado["falhas_tri7"], 1)


if __name__ == "__main__":
    unittest.main()
