import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.servicos.custas import extrair_pedidos_texto, validar_item_custas


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


if __name__ == "__main__":
    unittest.main()
