import json
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from backend.app.rotas.integracoes import (
    confirmar_custas_informadas_integracao,
    exigir_token_integracao_custas,
    listar_custas_pendentes_integracao,
)


def request(metodo: str, caminho: str) -> Request:
    return Request({"type": "http", "method": metodo, "path": caminho, "headers": []})


def conexao_simulada(cursor):
    cursor_contexto = MagicMock()
    cursor_contexto.__enter__.return_value = cursor
    conexao = MagicMock()
    conexao.cursor.return_value = cursor_contexto
    conexao_contexto = MagicMock()
    conexao_contexto.__enter__.return_value = conexao
    return conexao_contexto, conexao


class TesteIntegracaoCustas(unittest.TestCase):
    def test_token_exclusivo_e_obrigatorio(self):
        token = "a" * 43
        with patch.dict(os.environ, {"AERI_CUSTAS_API_TOKEN": token}):
            usuario = exigir_token_integracao_custas(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
            self.assertEqual(usuario, "INTEGRACAO_CUSTAS")
            with self.assertRaises(HTTPException) as erro:
                exigir_token_integracao_custas(HTTPAuthorizationCredentials(scheme="Bearer", credentials="errado"))
            self.assertEqual(erro.exception.status_code, 401)

    def test_pendentes_expoem_somente_pedido_e_tipo_da_certidao(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"pedido": "S26081052542D", "modalidade": "PENHOR", "resultado": "NEGATIVA"},
            {"pedido": "S26081052543D", "modalidade": "ALIENACAO_FIDUCIARIA", "resultado": "POSITIVA"},
            {"pedido": "S26081052544D", "modalidade": "PENHOR", "resultado": "POSITIVA"},
            {"pedido": "S26081052545D", "modalidade": "ALIENACAO_FIDUCIARIA", "resultado": "NEGATIVA"},
        ]
        contexto, conexao = conexao_simulada(cursor)
        with patch("backend.app.rotas.integracoes.conectar", return_value=contexto), \
             patch("backend.app.rotas.integracoes.registrar_auditoria_cursor"):
            resposta = listar_custas_pendentes_integracao(
                request("GET", "/api/integracoes/informar-custas/pendentes"),
                limite=500,
                usuario="INTEGRACAO_CUSTAS",
            )

        corpo = json.loads(resposta.body)
        self.assertEqual(corpo["itens"], [
            {"pedido": "S26081052542D", "tipoCertidao": "Penhor Negativo"},
            {"pedido": "S26081052543D", "tipoCertidao": "Alienação Fiduciária Positiva"},
            {"pedido": "S26081052544D", "tipoCertidao": "Penhor Positivo"},
            {"pedido": "S26081052545D", "tipoCertidao": "Alienação Fiduciária Negativa"},
        ])
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        conexao.commit.assert_called_once()

    def test_confirmacao_muda_somente_busca_realizada(self):
        ids = [uuid4(), uuid4()]
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [
                {"pedido": "S26081052542D", "status": "BUSCA_REALIZADA", "finalizado": False},
                {"pedido": "S26081052543D", "status": "CUSTAS_INFORMADAS", "finalizado": False},
                {"pedido": "S26081052544D", "status": "FAZER_PESQUISA", "finalizado": False},
            ],
            [{"id": ids[0], "pedido": "S26081052542D"}],
        ]
        contexto, _conexao = conexao_simulada(cursor)
        with patch("backend.app.rotas.integracoes.conectar", return_value=contexto), \
             patch("backend.app.rotas.integracoes.registrar_auditoria_cursor"):
            resposta = confirmar_custas_informadas_integracao(
                {
                    "pedidos": [
                        "S26081052542D",
                        "S26081052543D",
                        "S26081052544D",
                        "S26081052545D",
                    ]
                },
                request("POST", "/api/integracoes/informar-custas/confirmar"),
                usuario="INTEGRACAO_CUSTAS",
            )

        corpo = json.loads(resposta.body)
        self.assertEqual(corpo["confirmados"], ["S26081052542D"])
        self.assertEqual(corpo["jaConfirmados"], ["S26081052543D"])
        self.assertEqual(corpo["naoConfirmados"], ["S26081052544D"])
        self.assertEqual(corpo["naoEncontrados"], ["S26081052545D"])
        atualizacao = next(
            chamada for chamada in cursor.execute.call_args_list
            if "SET status='CUSTAS_INFORMADAS'" in chamada.args[0]
        )
        self.assertEqual(atualizacao.args[1], ("INTEGRACAO_CUSTAS", ["S26081052542D"]))


if __name__ == "__main__":
    unittest.main()
