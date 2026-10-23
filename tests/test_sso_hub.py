"""Fixtures sintéticas; não dependem de chaves ou contas de produção."""
import base64
import asyncio
import hashlib
import json
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from backend.app.autenticacao import COOKIE_SESSAO
from backend.app.rotas import sso_hub as rota
from backend.app.servicos.sso_hub import TicketHubInvalido, validar_ticket_hub

ORIGEM = "https://aeri-two.vercel.app"
HEADERS = {"Origin": ORIGEM, "Content-Type": "application/json"}
CAMINHO = "/api/auth/hub/exchange"


def b64(valor):
    return base64.urlsafe_b64encode(valor).decode().rstrip("=")


@pytest.fixture
def ambiente(monkeypatch):
    chave = Ed25519PrivateKey.generate()
    publica = chave.public_key().public_bytes_raw()
    kid = "sso-" + hashlib.sha256(publica).hexdigest()[:16]
    monkeypatch.setenv("AERI_HUB_SSO_PUBLIC_KEY_HEX", publica.hex())
    monkeypatch.setenv("AERI_HUB_SSO_KID", kid)
    claims = {"iss": "sync-hub", "aud": "aeri", "sub": str(uuid4()),
              "jti": str(uuid4()), "iat": int(time.time()), "exp": int(time.time()) + 60}
    header = {"typ": "JWT", "alg": "EdDSA", "kid": kid}

    def assinar(alteracoes=None, cabecalho=None, bruto=None):
        payload = bruto if bruto is not None else json.dumps({**claims, **(alteracoes or {})})
        mensagem = f"{b64(json.dumps(cabecalho or header).encode())}.{b64(payload.encode())}"
        return mensagem + "." + b64(chave.sign(mensagem.encode()))

    return assinar, claims, header


@pytest.fixture
def cliente():
    app = FastAPI()
    app.include_router(rota.router)
    with TestClient(app, base_url=ORIGEM) as client:
        yield client


@pytest.fixture
def banco():
    conexao = MagicMock()
    cursor = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [{"usuario": "CONTA_SINTETICA"}, {"jti": "consumido"}]
    with patch.object(rota, "preparar_banco"), patch.object(rota, "conectar", return_value=conexao), \
         patch.object(rota, "criar_sessao_cursor", return_value=("identificador-sintetico-novo", "csrf-sintetico")) as criar, \
         patch.object(rota, "registrar_auditoria_cursor"):
        yield conexao, cursor, criar


def test_ticket_valido(ambiente):
    assinar, claims, _ = ambiente
    assert validar_ticket_hub(assinar()).sub == claims["sub"]


@pytest.mark.parametrize("alteracao", [
    {"aud": "sync"}, {"aud": ["aeri"]}, {"iss": "outro"},
    {"exp": 1}, {"iat": True}, {"iat": "123"}, {"exp": False},
    {"sub": "login-em-vez-de-uuid"}, {"jti": "invalido"},
    {"iat": int(time.time()) + 100, "exp": int(time.time()) + 150},
    {"exp": int(time.time()) + 120}, {"nbf": True},
])
def test_claims_invalidas(ambiente, alteracao):
    assinar, _, _ = ambiente
    with pytest.raises(TicketHubInvalido):
        validar_ticket_hub(assinar(alteracao))


@pytest.mark.parametrize("campo,valor", [("kid", "desconhecido"), ("alg", "RS256"), ("typ", "outro"), ("crit", ["x"])])
def test_cabecalho_invalido(ambiente, campo, valor):
    assinar, _, header = ambiente
    with pytest.raises(TicketHubInvalido):
        validar_ticket_hub(assinar(cabecalho={**header, campo: valor}))


def test_assinatura_invalida_e_claim_duplicada(ambiente):
    assinar, claims, _ = ambiente
    ticket = assinar()
    with pytest.raises(TicketHubInvalido):
        validar_ticket_hub(ticket.rsplit(".", 1)[0] + "." + b64(bytes(64)))
    with pytest.raises(TicketHubInvalido):
        validar_ticket_hub(assinar(bruto=json.dumps(claims)[:-1] + ',"aud":"aeri"}'))


@pytest.mark.parametrize("anterior", [None, "sessao-outra-conta", "sessao-mesma-conta"])
def test_troca_cria_sessao_normal_e_revoga_anterior(ambiente, cliente, banco, anterior):
    _, cursor, criar = banco
    if anterior:
        cliente.cookies.set(COOKIE_SESSAO, anterior)
    resposta = cliente.post(CAMINHO, json={"ticket": ambiente[0]()}, headers=HEADERS)
    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
    cookie = resposta.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "Max-Age=28800" in cookie
    assert "Domain=" not in cookie
    criar.assert_called_once()
    assert criar.call_args.args[1] == "CONTA_SINTETICA"
    revogacoes = [c for c in cursor.execute.call_args_list if "UPDATE sessoes_aeri" in c.args[0]]
    assert len(revogacoes) == bool(anterior)
    if anterior:
        assert revogacoes[0].args[1] == (hashlib.sha256(anterior.encode()).hexdigest(),)
    banco[0].commit.assert_called_once()


@pytest.mark.parametrize("resultados", [[None], [{"usuario": "CONTA_SINTETICA"}, None]])
def test_conta_sem_vinculo_ou_replay_tem_mesma_resposta(ambiente, cliente, banco, resultados):
    banco[1].fetchone.side_effect = resultados
    r = cliente.post(CAMINHO, json={"ticket": ambiente[0]()}, headers=HEADERS)
    assert r.status_code == 401 and "set-cookie" not in r.headers
    assert r.json() == {"detail": rota.ERRO_ACESSO}
    banco[2].assert_not_called()
    banco[0].commit.assert_not_called()


@pytest.mark.parametrize("headers,corpo,status", [
    ({**HEADERS, "Origin": "https://outro.invalid"}, b'{}', 403),
    ({"Content-Type": "application/json"}, b'{}', 403),
    ({**HEADERS, "Host": "outro.invalid"}, b'{}', 403),
    ({**HEADERS, "Content-Type": "text/plain"}, b'{}', 415),
    (HEADERS, b'x' * 8193, 413),
    (HEADERS, b'{', 401),
    (HEADERS, b'{"ticket":"a","ticket":"b"}', 401),
    (HEADERS, b'{"ticket":"a","usuario":"qualquer"}', 401),
    (HEADERS, b'{"ticket":42}', 401),
])
def test_entrada_restrita_sem_acessar_banco(cliente, headers, corpo, status):
    with patch.object(rota, "preparar_banco") as preparar:
        r = cliente.post(CAMINHO, content=corpo, headers=headers)
    assert r.status_code == status
    assert "set-cookie" not in r.headers and "access-control-allow-origin" not in r.headers
    preparar.assert_not_called()


@pytest.mark.parametrize("metodo", ["get", "put", "patch", "delete", "options", "head"])
def test_apenas_post(cliente, metodo):
    assert cliente.request(metodo, CAMINHO).status_code == 405


def test_query_rejeitada(cliente):
    assert cliente.post(CAMINHO + "?ticket=nao-aceitar", json={}, headers=HEADERS).status_code == 400


def test_configuracao_ausente_nao_cria_sessao(ambiente, cliente, monkeypatch, banco):
    monkeypatch.delenv("AERI_HUB_SSO_PUBLIC_KEY_HEX")
    r = cliente.post(CAMINHO, json={"ticket": ambiente[0]()}, headers=HEADERS)
    assert r.status_code == 503 and "set-cookie" not in r.headers
    banco[2].assert_not_called()


def test_falha_de_banco_nao_emite_cookie_ou_vaza_detalhes(ambiente, cliente, banco):
    banco[1].execute.side_effect = rota.ErroPostgres("detalhe-sensivel-sintetico")
    r = cliente.post(CAMINHO, json={"ticket": ambiente[0]()}, headers=HEADERS)
    assert r.status_code == 503 and "set-cookie" not in r.headers
    assert "sensivel" not in r.text


def test_limite_funciona_sem_content_length_em_stream():
    partes = iter([b"x" * 4096, b"x" * 4097])

    async def receber():
        return {"type": "http.request", "body": next(partes), "more_body": True}

    request = Request({"type": "http", "method": "POST", "scheme": "https", "path": CAMINHO,
        "query_string": b"", "server": ("aeri-two.vercel.app", 443),
        "headers": [(b"host", b"aeri-two.vercel.app"), (b"origin", ORIGEM.encode()),
                    (b"content-type", b"application/json")]}, receive=receber)
    with pytest.raises(HTTPException) as erro:
        asyncio.run(rota._ler_entrada(request))
    assert erro.value.status_code == 413


def test_origin_duplicado_e_forwarded_host_nao_burlam_validacao(cliente):
    r = cliente.post(CAMINHO, content=b"{}", headers=[
        ("Origin", ORIGEM), ("Origin", "https://outro.invalid"), ("Content-Type", "application/json")])
    assert r.status_code == 403
    r = cliente.post(CAMINHO, json={}, headers={**HEADERS, "Host": "outro.invalid", "X-Forwarded-Host": "aeri-two.vercel.app"})
    assert r.status_code == 403


def test_expiracao_depois_de_esperar_lock_nao_consume_ticket(ambiente, cliente, banco):
    with patch.object(rota.time, "time", return_value=ambiente[1]["exp"] + 6), \
         patch.object(rota, "_ler_entrada") as ler:
        from backend.app.servicos.sso_hub import TicketHub
        ler.return_value = TicketHub(ambiente[1]["sub"], ambiente[1]["jti"], ambiente[1]["exp"])
        r = cliente.post(CAMINHO, json={}, headers=HEADERS)
    assert r.status_code == 401
    banco[2].assert_not_called()
    assert not any("INSERT INTO tickets" in c.args[0] for c in banco[1].execute.call_args_list)
