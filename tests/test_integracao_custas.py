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
    consultar_resultado_registro_auxiliar_integracao,
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

    def test_pendentes_expoem_registros_auxiliares_apenas_nas_positivas(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {"pedido": "S26081052542D", "modalidade": "PENHOR", "resultado": "NEGATIVA", "numero_registro": ""},
            {"pedido": "S26081052543D", "modalidade": "ALIENACAO_FIDUCIARIA", "resultado": "POSITIVA", "numero_registro": "12, 305"},
            {"pedido": "S26081052544D", "modalidade": "PENHOR", "resultado": "POSITIVA", "numero_registro": "87"},
            {"pedido": "S26081052545D", "modalidade": "ALIENACAO_FIDUCIARIA", "resultado": "NEGATIVA", "numero_registro": "999"},
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
            {"pedido": "S26081052542D", "tipoCertidao": "Penhor Negativo", "registrosAuxiliares": []},
            {"pedido": "S26081052543D", "tipoCertidao": "Alienação Fiduciária Positiva", "registrosAuxiliares": ["12", "305"]},
            {"pedido": "S26081052544D", "tipoCertidao": "Penhor Positivo", "registrosAuxiliares": ["87"]},
            {"pedido": "S26081052545D", "tipoCertidao": "Alienação Fiduciária Negativa", "registrosAuxiliares": []},
        ])
        self.assertEqual(resposta.headers["cache-control"], "no-store")
        conexao.commit.assert_called_once()

    def test_resultado_por_pedido_retorna_numeros_sem_dados_pessoais(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "pedido": "S26081052543D",
            "resultado": "POSITIVA",
            "numero_registro": "12, 305",
        }
        contexto, conexao = conexao_simulada(cursor)
        with patch("backend.app.rotas.integracoes.conectar", return_value=contexto), \
             patch("backend.app.rotas.integracoes.registrar_auditoria_cursor"):
            resposta = consultar_resultado_registro_auxiliar_integracao(
                "s26081052543d",
                request("GET", "/api/integracoes/informar-custas/resultado/S26081052543D"),
                usuario="INTEGRACAO_CUSTAS",
            )

        self.assertEqual(
            json.loads(resposta.body),
            {
                "pedido": "S26081052543D",
                "resultado": "POSITIVA",
                "registrosAuxiliares": ["12", "305"],
            },
        )
        self.assertIn("numero_registro", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], ("S26081052543D",))
        conexao.commit.assert_called_once()

    def test_resultado_por_pedido_rejeita_protocolo_invalido(self):
        with self.assertRaises(HTTPException) as erro:
            consultar_resultado_registro_auxiliar_integracao(
                "INVÁLIDO",
                request("GET", "/api/integracoes/informar-custas/resultado/INVÁLIDO"),
                usuario="INTEGRACAO_CUSTAS",
            )
        self.assertEqual(erro.exception.status_code, 422)

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
        self.assertIn("atualizado_por=NULL", atualizacao.args[0])
        self.assertEqual(atualizacao.args[1], (["S26081052542D"],))

        evento = next(
            chamada for chamada in cursor.execute.call_args_list
            if "CUSTAS_INFORMADAS_PELA_API" in chamada.args[0]
        )
        self.assertIsNone(evento.args[1][2])
        self.assertEqual(
            evento.args[1][3].obj,
            {"origem": "API_KEVIN", "ator": "INTEGRACAO_CUSTAS"},
        )


if __name__ == "__main__":
    unittest.main()
