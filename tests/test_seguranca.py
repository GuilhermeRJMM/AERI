import unittest
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

from fastapi import Request, Response

from backend.app.autenticacao import hash_senha, permissoes_sessao, senha_forte, verificar_senha
from backend.app.seguranca_web import (
    origem_sync_autorizada,
    origens_sync_autorizadas,
    politica_frame_ancestors,
    politica_samesite_sessao,
)
from backend.app.main import seguranca_http


class TesteSeguranca(unittest.TestCase):
    def test_argon2_valida_senha_sem_armazenar_texto(self):
        senha = "Senha-Forte-AERI-2026!"
        armazenada = hash_senha(senha)
        self.assertTrue(armazenada.startswith("$argon2id$"))
        self.assertNotIn(senha, armazenada)
        self.assertTrue(verificar_senha(senha, armazenada))
        self.assertFalse(verificar_senha("senha-errada", armazenada))

    def test_politica_recusa_senhas_fracas(self):
        self.assertTrue(senha_forte("Senha-Forte-AERI-2026!"))
        self.assertFalse(senha_forte("adm123"))
        self.assertFalse(senha_forte("somente-minusculas-2026"))

    def test_admin_tem_todas_as_permissoes(self):
        permissoes = permissoes_sessao({"perfil": "ADMIN"})

        self.assertTrue(all(permissoes.values()))

    def test_substituto_tem_permissoes_administrativas(self):
        permissoes = permissoes_sessao({"perfil": "SUBSTITUTO"})

        self.assertTrue(all(permissoes.values()))

    def test_operador_respeita_atribuicoes(self):
        permissoes = permissoes_sessao(
            {
                "perfil": "CONFERENTE",
                "pode_processar_matricula": True,
                "pode_processar_incra": False,
                "pode_gerenciar_custas": True,
                "pode_ver_intimacoes": True,
                "pode_criar_intimacoes": False,
                "pode_alterar_intimacoes": False,
                "pode_conferir_intimacoes": True,
            }
        )

        self.assertTrue(permissoes["processar_matricula"])
        self.assertFalse(permissoes["processar_incra"])
        self.assertTrue(permissoes["gerenciar_custas"])
        self.assertFalse(permissoes["criar_intimacoes"])
        self.assertTrue(permissoes["conferir_intimacoes"])

    def test_iframe_permanece_bloqueado_sem_origem_sync(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SYNC_ORIGIN", None)
            os.environ.pop("SYNC_ORIGINS", None)
            self.assertIsNone(origem_sync_autorizada())
            self.assertEqual(politica_frame_ancestors(), "'none'")
            self.assertEqual(politica_samesite_sessao(), "strict")

    def test_libera_somente_origem_https_exata_do_sync(self):
        with patch.dict(
            os.environ,
            {"SYNC_ORIGIN": "https://sync.cartorio.example/"},
        ):
            self.assertEqual(
                origem_sync_autorizada(),
                "https://sync.cartorio.example",
            )
            self.assertEqual(
                politica_frame_ancestors(),
                "'self' https://sync.cartorio.example",
            )
            self.assertEqual(politica_samesite_sessao(), "none")

    def test_libera_todos_os_ancestrais_internos_do_sync(self):
        with patch.dict(
            os.environ,
            {
                "SYNC_ORIGINS": (
                    "http://baseti.cri.local:3031,"
                    "http://localhost:3031"
                )
            },
        ):
            self.assertEqual(
                origens_sync_autorizadas(),
                (
                    "http://baseti.cri.local:3031",
                    "http://localhost:3031",
                ),
            )
            self.assertEqual(
                politica_frame_ancestors(),
                "'self' http://baseti.cri.local:3031 http://localhost:3031",
            )

    def test_lista_de_origens_falha_fechada_se_um_item_for_invalido(self):
        with patch.dict(
            os.environ,
            {
                "SYNC_ORIGINS": (
                    "http://sync.interno.local:3031,"
                    "https://host.example/caminho"
                )
            },
        ):
            self.assertEqual(origens_sync_autorizadas(), ())
            self.assertEqual(politica_frame_ancestors(), "'none'")

    def test_libera_http_somente_para_origem_interna_exata_do_sync(self):
        with patch.dict(
            os.environ,
            {"SYNC_ORIGIN": "http://sync.interno.local:3031"},
        ):
            self.assertEqual(
                origem_sync_autorizada(),
                "http://sync.interno.local:3031",
            )
            self.assertEqual(
                politica_frame_ancestors(),
                "'self' http://sync.interno.local:3031",
            )
            self.assertEqual(politica_samesite_sessao(), "none")

    def test_origem_sync_malformada_falha_fechada(self):
        invalidas = (
            "http://sync.cartorio.example",
            "https://sync.cartorio.example/caminho",
            "https://sync.cartorio.example; frame-src *",
            "https://sync.cartorio.example:porta-invalida",
        )
        for origem in invalidas:
            with self.subTest(origem=origem), patch.dict(
                os.environ,
                {"SYNC_ORIGIN": origem},
            ):
                self.assertIsNone(origem_sync_autorizada())
                self.assertEqual(politica_frame_ancestors(), "'none'")

    def test_vercel_nao_reintroduz_x_frame_options(self):
        raiz = Path(__file__).resolve().parent.parent
        configuracao = json.loads((raiz / "vercel.json").read_text(encoding="utf-8"))
        cabecalhos = {
            item["key"].lower(): item["value"]
            for grupo in configuracao.get("headers", [])
            for item in grupo.get("headers", [])
        }
        self.assertNotIn("x-frame-options", cabecalhos)
        self.assertIn("content-security-policy", cabecalhos)
        self.assertIn(
            "frame-ancestors 'self' http://baseti.cri.local:3031",
            cabecalhos["content-security-policy"],
        )
        self.assertIn(
            "http://localhost:3031",
            cabecalhos["content-security-policy"],
        )

    def test_middleware_libera_frame_apenas_para_sync_configurado(self):
        escopo = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("aeri.example", 443),
        }

        async def responder(_request):
            return Response(status_code=200)

        with patch.dict(
            os.environ,
            {"SYNC_ORIGIN": "https://sync.cartorio.example"},
        ):
            resposta = asyncio.run(seguranca_http(Request(escopo), responder))

        self.assertIn(
            "frame-ancestors 'self' https://sync.cartorio.example;",
            resposta.headers["content-security-policy"],
        )
        self.assertNotIn("x-frame-options", resposta.headers)


if __name__ == "__main__":
    unittest.main()
