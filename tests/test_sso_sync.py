import base64
import json
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.rotas import autenticacao
from backend.app.servicos.sso_sync import (
    SsoSyncConfiguracaoInvalida,
    SsoSyncTicketInvalido,
    validar_ticket_sync,
)


def _b64url(valor: bytes) -> str:
    return base64.urlsafe_b64encode(valor).decode("ascii").rstrip("=")


def _assinar_ticket(chave, claims: dict, cabecalho: dict | None = None) -> str:
    cabecalho = cabecalho or {"alg": "RS256", "typ": "JWT"}
    segmento_cabecalho = _b64url(json.dumps(cabecalho, separators=(",", ":")).encode())
    segmento_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    mensagem = f"{segmento_cabecalho}.{segmento_claims}".encode("ascii")
    assinatura = chave.sign(mensagem, padding.PKCS1v15(), hashes.SHA256())
    return f"{mensagem.decode()}.{_b64url(assinatura)}"


class _CursorFalso:
    def __init__(self, resultados):
        self.resultados = list(resultados)
        self.comandos = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, comando, parametros=None):
        self.comandos.append((comando, parametros))

    def fetchone(self):
        return self.resultados.pop(0) if self.resultados else None


class _ConexaoFalsa:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


class TesteSsoSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chave_privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem_publica = cls.chave_privada.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def setUp(self):
        self.ambiente = patch.dict(
            "os.environ",
            {
                "AERI_SYNC_SSO_PUBLIC_KEY_PEM": self.pem_publica,
                "AERI_SYNC_SSO_ISSUER": "sync-teste",
                "AERI_SYNC_SSO_AUDIENCE": "aeri-teste",
            },
            clear=False,
        )
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)
        self.agora = int(time.time())

    def _claims(self, **sobrescritos):
        claims = {
            "iss": "sync-teste",
            "aud": "aeri-teste",
            "sub": "  usuario.teste  ",
            "iat": self.agora,
            "exp": self.agora + 60,
            "jti": "jti-aleatorio-com-mais-de-16",
            "amr": ["pwd", "mfa"],
        }
        claims.update(sobrescritos)
        return claims

    def _ticket(self, claims=None, chave=None, cabecalho=None):
        return _assinar_ticket(chave or self.chave_privada, claims or self._claims(), cabecalho)

    def test_valida_ticket_e_retorna_apenas_identidade_e_hash(self):
        ticket = validar_ticket_sync(self._ticket(), agora=self.agora)

        self.assertEqual(ticket.usuario, "USUARIO.TESTE")
        self.assertEqual(len(ticket.jti_hash), 64)
        self.assertNotIn("jti-aleatorio", ticket.jti_hash)
        self.assertEqual(ticket.expira_em, self.agora + 60)
        self.assertEqual(ticket.metodos_autenticacao, frozenset({"pwd", "mfa"}))

    def test_recusa_ticket_sem_chave_publica_configurada(self):
        with patch.dict("os.environ", {"AERI_SYNC_SSO_PUBLIC_KEY_PEM": ""}):
            with self.assertRaises(SsoSyncConfiguracaoInvalida):
                validar_ticket_sync(self._ticket(), agora=self.agora)

    def test_recusa_assinatura_issuer_audiencia_algoritmo_e_validades_invalidos(self):
        outra_chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        casos = [
            (self._ticket(chave=outra_chave), SsoSyncTicketInvalido),
            (self._ticket(self._claims(iss="outro")), SsoSyncTicketInvalido),
            (self._ticket(self._claims(aud="outro")), SsoSyncTicketInvalido),
            (self._ticket(cabecalho={"alg": "HS256", "typ": "JWT"}), SsoSyncTicketInvalido),
            (self._ticket(self._claims(exp=self.agora - 30)), SsoSyncTicketInvalido),
            (self._ticket(self._claims(exp=self.agora + 91)), SsoSyncTicketInvalido),
            (self._ticket(self._claims(iat=self.agora + 30, exp=self.agora + 60)), SsoSyncTicketInvalido),
            (self._ticket(self._claims(nbf=self.agora + 30)), SsoSyncTicketInvalido),
        ]
        for token, erro in casos:
            with self.subTest(token=token[:20]):
                with self.assertRaises(erro):
                    validar_ticket_sync(token, agora=self.agora)

    def test_recusa_ticket_malformado(self):
        for token in ("", "a.b", "a.b.c", "a.@@.c", "x" * 9000):
            with self.subTest(token=token[:20]):
                with self.assertRaises(SsoSyncTicketInvalido):
                    validar_ticket_sync(token, agora=self.agora)

    def test_endpoint_cria_sessao_aeri_e_recusa_reutilizacao(self):
        ticket = self._ticket()
        cursor = _CursorFalso([
            {"jti_hash": "hash"},
            {
                "usuario": "USUARIO.TESTE",
                "nome": "Usuário de Teste",
                "perfil": "CERTIDAO",
                "ativo": True,
                "mfa_ativo": True,
            },
        ])
        conexao = _ConexaoFalsa(cursor)

        @contextmanager
        def conectar_falso():
            yield conexao

        app = FastAPI()
        app.include_router(autenticacao.router)
        with (
            patch.object(autenticacao, "preparar_banco"),
            patch.object(autenticacao, "conectar", conectar_falso),
            patch.object(autenticacao, "permissoes_efetivas_cursor", return_value={"certidao": True}),
            patch.object(autenticacao, "criar_sessao_cursor", return_value=("sessao-secreta", "csrf-secreto")),
            patch.object(autenticacao, "registrar_auditoria_cursor"),
            patch.object(autenticacao, "politica_samesite_sessao", return_value="strict"),
            TestClient(app, follow_redirects=False) as cliente,
        ):
            resposta = cliente.post(
                "/api/login/sync",
                data={"ticket": ticket},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            self.assertEqual(resposta.status_code, 303)
            self.assertEqual(resposta.headers["location"], "/")
            self.assertIn("HttpOnly", resposta.headers["set-cookie"])
            self.assertIn("Secure", resposta.headers["set-cookie"])
            self.assertIn("SameSite=lax", resposta.headers["set-cookie"])
            self.assertEqual(resposta.headers["cache-control"], "no-store")
            self.assertEqual(conexao.commits, 1)

        cursor_repetido = _CursorFalso([None])
        conexao_repetida = _ConexaoFalsa(cursor_repetido)

        @contextmanager
        def conectar_repetido():
            yield conexao_repetida

        with (
            patch.object(autenticacao, "preparar_banco"),
            patch.object(autenticacao, "conectar", conectar_repetido),
            patch.object(autenticacao, "registrar_auditoria_cursor"),
            TestClient(app, follow_redirects=False) as cliente,
        ):
            resposta_repetida = cliente.post(
                "/api/login/sync",
                data={"ticket": ticket},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        self.assertEqual(resposta_repetida.status_code, 409)
        self.assertEqual(conexao_repetida.commits, 1)

    def test_mfa_aeri_nao_pode_ser_burlado_por_ticket_sem_amr_mfa(self):
        ticket = self._ticket(self._claims(amr=["pwd"]))
        cursor = _CursorFalso([
            {"jti_hash": "hash"},
            {"usuario": "USUARIO.TESTE", "mfa_ativo": True},
        ])
        conexao = _ConexaoFalsa(cursor)

        @contextmanager
        def conectar_falso():
            yield conexao

        app = FastAPI()
        app.include_router(autenticacao.router)
        with (
            patch.object(autenticacao, "preparar_banco"),
            patch.object(autenticacao, "conectar", conectar_falso),
            patch.object(autenticacao, "criar_sessao_cursor") as criar_sessao,
            patch.object(autenticacao, "registrar_auditoria_cursor"),
            TestClient(app, follow_redirects=False) as cliente,
        ):
            resposta = cliente.post("/api/login/sync", data={"ticket": ticket})

        self.assertEqual(resposta.status_code, 403)
        criar_sessao.assert_not_called()
        self.assertEqual(conexao.commits, 1)


if __name__ == "__main__":
    unittest.main()
