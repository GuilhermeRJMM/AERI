import unittest
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from backend.app.rotas.custas import _analisar_versao_esperada
from pypdf import PdfReader

from backend.app.servicos.custas import extrair_pedidos_texto, gerar_relatorio_custas_pdf, validar_item_custas


def bloco(pedido: str, observacao: str, nome="PESSOA DE TESTE", documento="12345678901") -> str:
    return f"""
    P26080000001D {pedido} 04/08/2026 09:00:00 Livro 3 - Garantias
    Dados do Pedido
    Tipo: Pessoa Física, Nome / Razão: {nome}, CPF / CNPJ: {documento}, RG / IE:
    Observações: {observacao}
    Observações
    {observacao}
    Solicitante Email Solicitante CPF Telefone
    """


class TesteInformarCustas(unittest.TestCase):
    def test_relatorio_pdf_usa_formato_simples_e_ordem_recebida(self):
        pdf = gerar_relatorio_custas_pdf([
            {"pedido": "S26081052542D", "modalidade": "PENHOR", "resultado": "NEGATIVA"},
            {"pedido": "S26081052543D", "modalidade": "ALIENACAO_FIDUCIARIA", "resultado": "POSITIVA"},
        ])
        self.assertTrue(pdf.startswith(b"%PDF-"))
        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("Número do pedido: S26081052542D\nImportação: Penhor Negativo", texto)
        self.assertIn("Número do pedido: S26081052543D\nImportação: Alienação Fiduciária Positiva", texto)
        self.assertLess(texto.index("S26081052542D"), texto.index("S26081052543D"))

    def test_extrai_penhor_e_formata_cpf(self):
        resultado = extrair_pedidos_texto(bloco(
            "S26080000001D", "CERTIDÃO DE PENHOR - CULTURA: SOJA - SAFRA: 2026/2027"
        ))

        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["itens"][0]["modalidade"], "PENHOR")
        self.assertEqual(resultado["itens"][0]["produto"], "SOJA")
        self.assertEqual(resultado["itens"][0]["safra"], "2026/2027")
        self.assertEqual(resultado["itens"][0]["documento"], "123.456.789-01")

    def test_extrai_alienacao_e_safra_separada_por_espaco(self):
        resultado = extrair_pedidos_texto(bloco(
            "S26080000002D", "CERTIDÃO DE ALIENAÇÃO FIDUCIÁRIA - SAFRA 2025 2026 - PRODUTO SOJA EM GRÃOS"
        ))

        item = resultado["itens"][0]
        self.assertEqual(item["modalidade"], "ALIENACAO_FIDUCIARIA")
        self.assertEqual(item["produto"], "SOJA")
        self.assertEqual(item["safra"], "2025/2026")

    def test_extrai_alienacao_de_graos_sem_palavra_fiduciaria(self):
        resultado = extrair_pedidos_texto(bloco(
            "S26080000008D", "CERTIDÃO DE ALIENAÇÃO DE GRÃOS DE SOJA SAFRA 2025/2026"
        ))

        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["itens"][0]["modalidade"], "ALIENACAO_FIDUCIARIA")

    def test_extrai_safra_quando_produto_aparece_entre_rotulo_e_ano(self):
        resultado = extrair_pedidos_texto(bloco(
            "S26080000010D", "CERTIDÃO DE PENHOR SAFRA SOJA 2026/2027"
        ))

        self.assertEqual(resultado["itens"][0]["produto"], "SOJA")
        self.assertEqual(resultado["itens"][0]["safra"], "2026/2027")

    def test_inclui_estufas_do_livro_tres_como_garantia(self):
        resultado = extrair_pedidos_texto(bloco(
            "S26080000009D", "1 (uma) Estufa, fabricante Florida Estufas Agrícolas"
        ))

        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["itens"][0]["modalidade"], "PENHOR")
        self.assertEqual(resultado["itens"][0]["produto"], "ESTUFAS")
        self.assertEqual(resultado["itens"][0]["safra"], "NÃO SE APLICA")
        self.assertEqual(resultado["alertas"], [])

    def test_deduplica_repeticao_do_mesmo_pedido(self):
        texto = bloco("S26080000003D", "PENHOR DE MILHO - SAFRA 2026-27")
        resultado = extrair_pedidos_texto(texto + texto)

        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["itens"][0]["safra"], "2026/2027")

    def test_ignora_certidoes_fora_do_informar_custas(self):
        casos = (
            "CERTIDÃO VINTENÁRIA DO IMÓVEL",
            "CERTIDÃO DE DOCUMENTO ARQUIVADO",
            "CERTIDÃO DE PACTO ANTENUPCIAL",
        )
        for indice, descricao in enumerate(casos, start=4):
            with self.subTest(descricao=descricao):
                texto = bloco(f"S260800000{indice:02d}D", descricao)
                resultado = extrair_pedidos_texto(texto)
                self.assertEqual(resultado["total"], 0)
                self.assertEqual(resultado["ignorados"], 1)

    def test_preserva_dois_pedidos_da_mesma_pessoa_produto_e_safra(self):
        primeiro = bloco("S26080000101D", "CERTIDÃO DE PENHOR - CULTURA: SOJA - SAFRA: 2026/2027")
        segundo = bloco("S26080000102D", "CERTIDÃO DE PENHOR - CULTURA: SOJA - SAFRA: 2026/2027")

        resultado = extrair_pedidos_texto(primeiro + segundo)

        self.assertEqual(resultado["total"], 2)
        self.assertEqual(
            [item["pedido"] for item in resultado["itens"]],
            ["S26080000101D", "S26080000102D"],
        )

    def test_campo_ausente_fica_sinalizado_para_revisao(self):
        resultado = extrair_pedidos_texto(bloco("S26080000005D", "CERTIDÃO DE PENHOR - SAFRA 2026/2027"))

        self.assertEqual(resultado["itens"][0]["produto"], "NÃO CONSTA")
        self.assertEqual(resultado["alertas"], [{"pedido": "S26080000005D", "campos": ["produto"]}])

    def test_pesquisa_positiva_exige_numero_do_registro(self):
        with self.assertRaises(HTTPException) as erro:
            validar_item_custas({
                "nome": "PESSOA DE TESTE", "documento": "12345678901", "modalidade": "PENHOR",
                "produto": "SOJA", "safra": "2026/2027", "resultado": "POSITIVA",
                "numeroRegistro": "", "status": "BUSCA_REALIZADA",
            })

        self.assertEqual(erro.exception.status_code, 422)

    def test_migracao_cria_filas_e_auditoria(self):
        sql = (Path(__file__).parents[1] / "backend/app/migrations/014_informar_custas.sql").read_text(encoding="utf-8")

        self.assertIn("custas_livro3_aeri", sql)
        self.assertIn("eventos_custas_livro3_aeri", sql)
        self.assertIn("pode_gerenciar_custas", sql)
        self.assertIn("finalizado BOOLEAN", sql)

    def test_versao_esperada_aceita_iso_valido(self):
        versao = _analisar_versao_esperada(
            {"atualizadoEm": "2026-08-06T21:23:45.123456+00:00"}
        )

        self.assertEqual(
            versao,
            datetime(2026, 8, 6, 21, 23, 45, 123456, tzinfo=timezone.utc),
        )

    def test_versao_esperada_rejeita_valor_ausente_ou_invalido(self):
        for dados in ({}, {"atualizadoEm": "nao-e-uma-data"}, {"atualizadoEm": None}):
            with self.subTest(dados=dados):
                with self.assertRaises(HTTPException) as erro:
                    _analisar_versao_esperada(dados)
                self.assertEqual(erro.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
