import unittest
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request

from backend.app.rotas.custas import _analisar_versao_esperada, exportar_relatorio_custas
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

    def test_exportar_promove_todas_as_buscas_realizadas_para_custas_informadas(self):
        relatorio_id = uuid4()
        outros_ids = [uuid4(), uuid4()]
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [{
                "id": relatorio_id,
                "pedido": "S26081052542D",
                "modalidade": "PENHOR",
                "resultado": "NEGATIVA",
            }],
            [
                {"id": outros_ids[0], "pedido": "S26081052543D"},
                {"id": outros_ids[1], "pedido": "S26081052544D"},
            ],
        ]
        cursor_contexto = MagicMock()
        cursor_contexto.__enter__.return_value = cursor
        conexao = MagicMock()
        conexao.cursor.return_value = cursor_contexto
        conexao_contexto = MagicMock()
        conexao_contexto.__enter__.return_value = conexao
        request = Request({"type": "http", "method": "POST", "path": "/api/custas/relatorio", "headers": []})

        with patch("backend.app.rotas.custas.conectar", return_value=conexao_contexto), \
             patch("backend.app.rotas.custas._registrar_evento") as registrar_evento, \
             patch("backend.app.rotas.custas.registrar_auditoria_cursor") as auditar:
            resposta = exportar_relatorio_custas(
                {"ids": [str(relatorio_id)]}, request, usuario="AUDITOR"
            )

        atualizacao = next(
            chamada for chamada in cursor.execute.call_args_list
            if "SET status='CUSTAS_INFORMADAS'" in chamada.args[0]
        )
        self.assertIn("WHERE status='BUSCA_REALIZADA' AND finalizado=FALSE", atualizacao.args[0])
        self.assertEqual(atualizacao.args[1], ("AUDITOR",))
        self.assertEqual(registrar_evento.call_count, 2)
        self.assertEqual(resposta.headers["x-aeri-custas-informadas"], "2")
        self.assertEqual(resposta.media_type, "application/pdf")
        auditar.assert_called_once()

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


class TesteImportacaoPesquisaAutomatica(unittest.TestCase):
    """A pesquisa no Registro Auxiliar entra junto com a importação.

    Antes o conferente importava o relatório e depois clicava "Pesquisar" em
    cada pedido. A consulta é local, no índice já sincronizado, então roda na
    mesma transação da importação.
    """

    def _importar(self, itens, encontrados):
        import asyncio
        from decimal import Decimal
        from backend.app.rotas import custas as rotas

        novos = [{"id": uuid4(), **item} for item in itens]
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[], []]          # existentes, todos
        cursor.fetchone.side_effect = list(novos)       # um INSERT ... RETURNING por item
        cursor_contexto = MagicMock()
        cursor_contexto.__enter__.return_value = cursor
        conexao = MagicMock()
        conexao.cursor.return_value = cursor_contexto
        conexao_contexto = MagicMock()
        conexao_contexto.__enter__.return_value = conexao

        pdf = b"%PDF-1.4\ncorpo de teste\n%%EOF"

        async def receive():
            return {"type": "http.request", "body": pdf, "more_body": False}

        request = Request(
            {"type": "http", "method": "POST", "path": "/api/custas/importar",
             "headers": [(b"content-length", str(len(pdf)).encode())]},
            receive,
        )
        extraido = {"itens": itens, "alertas": [], "ignorados": 0, "total": len(itens)}

        def buscar(_cursor, pedido, _usuario, _preco=None):
            numeros = encontrados.get(pedido["pedido"], [])
            return {"item": {"id": str(pedido["id"]), "pedido": pedido["pedido"],
                             "status": "BUSCA_REALIZADA",
                             "resultado": "POSITIVA" if numeros else "NEGATIVA"},
                    "registros": numeros, "valor": 139.93 * max(1, len(numeros)),
                    "resultado": "POSITIVA" if numeros else "NEGATIVA"}

        with patch.object(rotas, "extrair_pedidos_pdf", return_value=extraido), \
             patch.object(rotas, "conectar", return_value=conexao_contexto), \
             patch.object(rotas, "_registrar_evento"), \
             patch.object(rotas, "registrar_auditoria_cursor"), \
             patch.object(rotas, "_preco_certidao_registro_auxiliar", return_value=Decimal("139.93")), \
             patch.object(rotas, "_pesquisar_registros", side_effect=buscar) as pesquisa:
            resposta = asyncio.run(
                rotas.importar_relatorio(request, confirmar=True, usuario="AUDITOR")
            )
        return resposta, pesquisa, novos

    def _itens(self):
        return [
            {"pedido": "S26081052542D", "nome": "PESSOA UM", "documento": "12345678901",
             "modalidade": "PENHOR", "produto": "SOJA", "safra": "2025/2026"},
            {"pedido": "S26081052543D", "nome": "PESSOA DOIS", "documento": "12345678902",
             "modalidade": "ALIENACAO_FIDUCIARIA", "produto": "MILHO", "safra": "2025/2026"},
        ]

    def test_pesquisa_roda_uma_vez_por_pedido_importado(self):
        itens = self._itens()
        resposta, pesquisa, _novos = self._importar(itens, {"S26081052542D": [7, 9]})
        self.assertEqual(pesquisa.call_count, 2, "cada pedido novo precisa ser pesquisado")
        pedidos = [chamada.args[1]["pedido"] for chamada in pesquisa.call_args_list]
        self.assertEqual(pedidos, [item["pedido"] for item in itens])
        # O preco e lido uma vez e repassado, para nao consultar a tabela por pedido.
        self.assertTrue(all(chamada.args[3] is not None for chamada in pesquisa.call_args_list))

    def test_resposta_traz_o_resultado_da_pesquisa_e_o_item_ja_atualizado(self):
        resposta, _pesquisa, _novos = self._importar(self._itens(), {"S26081052542D": [7, 9]})
        self.assertEqual(resposta["importados"], 2)
        self.assertEqual(resposta["pesquisados"], 2)
        self.assertEqual(resposta["positivas"], 1)
        self.assertEqual(resposta["negativas"], 1)
        # 139,93 x 2 registros na positiva + 139,93 na negativa
        self.assertEqual(resposta["valorTotal"], 419.79)
        # O item devolvido e o de DEPOIS da pesquisa: a tela ja mostra o resultado.
        self.assertTrue(all(item["status"] == "BUSCA_REALIZADA" for item in resposta["itensImportados"]))
        self.assertEqual(
            sorted(item["resultado"] for item in resposta["itensImportados"]),
            ["NEGATIVA", "POSITIVA"],
        )

    def test_previa_nao_pesquisa_nada(self):
        """Sem confirmar, a importação só mostra o que veio no PDF."""
        import asyncio
        from backend.app.rotas import custas as rotas
        itens = self._itens()
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[], []]
        cursor_contexto = MagicMock()
        cursor_contexto.__enter__.return_value = cursor
        conexao = MagicMock()
        conexao.cursor.return_value = cursor_contexto
        conexao_contexto = MagicMock()
        conexao_contexto.__enter__.return_value = conexao
        pdf = b"%PDF-1.4\ncorpo\n%%EOF"

        async def receive():
            return {"type": "http.request", "body": pdf, "more_body": False}

        request = Request({"type": "http", "method": "POST", "path": "/api/custas/importar",
                           "headers": [(b"content-length", str(len(pdf)).encode())]}, receive)
        with patch.object(rotas, "extrair_pedidos_pdf",
                          return_value={"itens": itens, "alertas": [], "ignorados": 0, "total": 2}), \
             patch.object(rotas, "conectar", return_value=conexao_contexto), \
             patch.object(rotas, "_pesquisar_registros") as pesquisa:
            resposta = asyncio.run(rotas.importar_relatorio(request, confirmar=False, usuario="AUDITOR"))
        pesquisa.assert_not_called()
        self.assertEqual(resposta["importados"], 0)


class TestePesquisaRegistroAuxiliar(unittest.TestCase):
    """Fixa o comportamento da pesquisa depois de extraí-la da rota.

    Ela passou a ser compartilhada com a importação, então uma mudança aqui
    afeta os dois caminhos.
    """

    def _pesquisar(self, pedido, numeros):
        from decimal import Decimal
        from backend.app.rotas import custas as rotas
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"numero": n} for n in numeros]
        cursor.fetchone.return_value = {**pedido, "resultado": "POSITIVA" if numeros else "NEGATIVA"}
        # hash_documento exige AERI_BUSCAS_HMAC_KEY e falha fechado sem ela --
        # comportamento correto; aqui interessa a forma da consulta.
        with patch.object(rotas, "_registrar_evento") as evento, \
             patch.object(rotas, "hash_documento", return_value="hash-de-teste"), \
             patch.object(rotas, "custas_json", side_effect=lambda linha: linha):
            saida = rotas._pesquisar_registros(cursor, pedido, "AUDITOR", Decimal("139.93"))
        consultas = [c.args[0] for c in cursor.execute.call_args_list]
        parametros = [c.args[1] if len(c.args) > 1 else () for c in cursor.execute.call_args_list]
        return saida, consultas, parametros, evento

    def _pedido(self, **extra):
        base = {"id": uuid4(), "pedido": "S26081052542D", "nome": "PESSOA DE TESTE",
                "documento": "12345678901", "modalidade": "PENHOR",
                "produto": "SOJA", "safra": "2025/2026"}
        base.update(extra)
        return base

    def test_positiva_grava_os_numeros_e_o_status(self):
        saida, consultas, parametros, evento = self._pesquisar(self._pedido(), [7, 9])
        self.assertEqual(saida["resultado"], "POSITIVA")
        self.assertEqual(saida["registros"], [7, 9])
        self.assertEqual(saida["valor"], 279.86)   # 139,93 por registro
        atualizacao = next(c for c in consultas if "SET resultado=" in c)
        self.assertIn("status='BUSCA_REALIZADA'", atualizacao)
        gravados = parametros[consultas.index(atualizacao)]
        self.assertEqual(gravados[1], "7, 9")
        evento.assert_called_once()

    def test_negativa_cobra_uma_certidao_e_nao_zero(self):
        saida, _c, _p, _e = self._pesquisar(self._pedido(), [])
        self.assertEqual(saida["resultado"], "NEGATIVA")
        self.assertEqual(saida["valor"], 139.93)

    def test_alienacao_fiduciaria_consulta_o_rotulo_do_registro_auxiliar(self):
        # No Informar Custas a modalidade e ALIENACAO_FIDUCIARIA; no Registro
        # Auxiliar o rotulo gravado e "ALIENAÇÃO".
        _s, consultas, parametros, _e = self._pesquisar(
            self._pedido(modalidade="ALIENACAO_FIDUCIARIA"), [])
        busca = next(c for c in consultas if "registros_auxiliares_aeri" in c)
        self.assertIn("ALIENAÇÃO", parametros[consultas.index(busca)])

    def test_documento_valido_amplia_a_busca_para_o_hash(self):
        _s, consultas, _p, _e = self._pesquisar(self._pedido(documento="123.456.789-01"), [])
        busca = next(c for c in consultas if "registros_auxiliares_aeri" in c)
        self.assertIn("documentos_hash ? %s", busca)

    def test_documento_invalido_busca_apenas_por_nome(self):
        _s, consultas, _p, _e = self._pesquisar(self._pedido(documento="NAO CONSTA"), [])
        busca = next(c for c in consultas if "registros_auxiliares_aeri" in c)
        self.assertNotIn("documentos_hash", busca)
        self.assertIn("nomes_busca LIKE %s", busca)
