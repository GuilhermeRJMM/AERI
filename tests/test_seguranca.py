import unittest
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, Request, Response

from backend.app.autenticacao import (
    COOKIE_SESSAO,
    _derivar_csrf,
    exigir_permissao,
    hash_senha,
    permissoes_sessao,
    proteger_csrf,
    senha_forte,
    usuario_atual,
    verificar_senha,
)
from backend.app.seguranca_web import (
    ip_cliente,
    origem_sync_autorizada,
    origens_sync_autorizadas,
    politica_frame_ancestors,
    politica_samesite_sessao,
)
from backend.app.main import seguranca_http
from backend.app.rotas.usuarios import _validar_permissoes


def _requisicao_com_cabecalhos(cabecalhos: dict[str, str]) -> Request:
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
        "headers": [
            (chave.lower().encode(), valor.encode())
            for chave, valor in cabecalhos.items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("aeri.example", 443),
    }
    return Request(escopo)


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

    def test_auditor_recebe_somente_acessos_registrais(self):
        permissoes = permissoes_sessao({
            "perfil": "AUDITOR",
            "pode_processar_matricula": False,
            "pode_revisar_auditoria": False,
            "pode_acessar_mapa_onr": False,
            "pode_gerenciar_custas": True,
        })

        self.assertTrue(permissoes["processar_matricula"])
        self.assertTrue(permissoes["revisar_auditoria"])
        self.assertFalse(permissoes["acessar_mapa_onr"])
        self.assertFalse(permissoes["processar_incra"])
        self.assertFalse(permissoes["gerenciar_custas"])
        self.assertFalse(permissoes["ver_intimacoes"])

    def test_auditor_acessa_pendencias_mas_nao_custas(self):
        request = SimpleNamespace(state=SimpleNamespace(sessao={
            "perfil": "AUDITOR",
            "deve_trocar_senha": False,
            "pode_revisar_auditoria": False,
            "pode_acessar_mapa_onr": False,
            "pode_gerenciar_custas": True,
        }))

        self.assertEqual(
            exigir_permissao("revisar_auditoria")(request, "AUDITOR_TESTE"),
            "AUDITOR_TESTE",
        )
        with self.assertRaises(HTTPException) as erro:
            exigir_permissao("gerenciar_custas")(request, "AUDITOR_TESTE")
        self.assertEqual(erro.exception.status_code, 403)

    def test_mapa_onr_e_permissao_opcional_do_auditor(self):
        sessao = {
            "perfil": "AUDITOR",
            "deve_trocar_senha": False,
            "pode_acessar_mapa_onr": True,
        }
        request = SimpleNamespace(state=SimpleNamespace(sessao=sessao))

        self.assertTrue(permissoes_sessao(sessao)["acessar_mapa_onr"])
        self.assertEqual(
            exigir_permissao("acessar_mapa_onr")(request, "AUDITOR_TESTE"),
            "AUDITOR_TESTE",
        )

    def test_validacao_do_auditor_preserva_mapa_e_bloqueia_outros_opcionais(self):
        permissoes = _validar_permissoes({
            "permissoes": {
                "acessar_mapa_onr": True,
                "gerenciar_custas": True,
            }
        }, "AUDITOR")

        self.assertTrue(permissoes["pode_processar_matricula"])
        self.assertTrue(permissoes["pode_revisar_auditoria"])
        self.assertTrue(permissoes["pode_acessar_mapa_onr"])
        self.assertFalse(permissoes["pode_gerenciar_custas"])

    def test_csrf_derivado_e_igual_em_qualquer_aba_da_mesma_sessao(self):
        # Antes, o csrf era um valor aleatório re-gerado a cada checagem de
        # sessão e sobrescrevia o único válido no banco: abrir uma 2ª aba
        # invalidava o token que a 1ª aba já tinha guardado em memória,
        # quebrando a próxima ação nela com "validação de segurança
        # expirada". Sendo determinístico a partir do token de sessão
        # (idêntico em todas as abas via cookie), qualquer aba recalcula o
        # mesmo csrf, sem depender de sincronização entre elas.
        token_sessao = "token-de-sessao-compartilhado-pelo-cookie"

        csrf_aba_1 = _derivar_csrf(token_sessao)
        csrf_aba_2 = _derivar_csrf(token_sessao)

        self.assertEqual(csrf_aba_1, csrf_aba_2)

    def test_csrf_derivado_difere_entre_sessoes_distintas(self):
        self.assertNotEqual(_derivar_csrf("sessao-a"), _derivar_csrf("sessao-b"))

    def test_proteger_csrf_e_usuario_atual_reaproveitam_a_mesma_busca_de_sessao(self):
        # proteger_csrf roda antes de usuario_atual em toda rota de escrita
        # (ex.: salvar um pedido em Informar Custas). Antes, cada um buscava
        # a sessão no banco por conta própria -- duas conexões novas e duas
        # consultas redundantes por clique. Agora devem compartilhar a
        # mesma busca via request.state.sessao.
        token_sessao = "token-de-sessao-teste"
        requisicao = _requisicao_com_cabecalhos({
            "cookie": f"{COOKIE_SESSAO}={token_sessao}",
            "x-csrf-token": _derivar_csrf(token_sessao),
        })
        sessao_falsa = {
            "usuario": "conferente",
            "perfil": "CONFERENTE",
            "deve_trocar_senha": False,
            "pode_gerenciar_custas": True,
        }
        with patch(
            "backend.app.autenticacao._obter_sessao", return_value=sessao_falsa
        ) as mock_obter_sessao:
            proteger_csrf(requisicao)
            usuario = usuario_atual(requisicao)

        self.assertEqual(usuario, "conferente")
        mock_obter_sessao.assert_called_once()

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

    def test_ip_cliente_usa_o_ultimo_salto_do_x_forwarded_for(self):
        # O último salto é escrito pelo proxy confiável (Vercel); os
        # anteriores vêm do próprio cliente e são livremente forjáveis. Usar
        # o primeiro permitia burlar o bloqueio de tentativas de login
        # trocando esse valor a cada requisição.
        requisicao = _requisicao_com_cabecalhos(
            {"x-forwarded-for": "1.2.3.4, 5.6.7.8, 203.0.113.9"}
        )
        self.assertEqual(ip_cliente(requisicao), "203.0.113.9")

    def test_ip_cliente_usa_ip_da_conexao_sem_x_forwarded_for(self):
        requisicao = _requisicao_com_cabecalhos({})
        self.assertEqual(ip_cliente(requisicao), "127.0.0.1")

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
