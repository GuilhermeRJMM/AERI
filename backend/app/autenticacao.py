import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from backend.app.database import conectar
from backend.app.permissoes import (
    COLUNAS_LEGADAS,
    PERMISSOES,
    PERMISSOES_AUDITOR,
    PERMISSOES_OPCIONAIS_AUDITOR,
    permissoes_relacionais_do_registro,
)
from backend.app.seguranca_web import ip_cliente, validar_origem


COOKIE_SESSAO = "__Host-aeri_sessao"
SESSAO_SEGUNDOS = 60 * 60 * 8
INATIVIDADE_SEGUNDOS = 60 * 30
MAX_TENTATIVAS = 5
JANELA_TENTATIVAS_MINUTOS = 15
PERFIS_ADMINISTRATIVOS = {"ADMIN", "SUBSTITUTO"}
_argon2 = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)
_HASH_SIMULADO = _argon2.hash("senha-inexistente-para-tempo-constante")


TAMANHO_MINIMO_SENHA = 10


def senha_forte(senha: str) -> bool:
    """Mínimo de 10 caracteres, com ao menos uma maiúscula, um número e um
    símbolo. As senhas já existentes, criadas sob o mínimo anterior de 14,
    continuam válidas: a regra ficou menos restritiva, não diferente."""
    return (
        len(senha) >= TAMANHO_MINIMO_SENHA
        and any(c.isupper() for c in senha)
        and any(c.isdigit() for c in senha)
        and any(not c.isalnum() for c in senha)
    )


def hash_senha(senha: str) -> str:
    return _argon2.hash(senha)


def verificar_senha(senha: str, armazenada: str) -> bool:
    if armazenada.startswith("$argon2id$"):
        try:
            return _argon2.verify(armazenada, senha)
        except (VerifyMismatchError, InvalidHashError):
            return False
    try:
        algoritmo, salt_b64, hash_b64 = armazenada.split("$", 2)
        if algoritmo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        esperado = base64.urlsafe_b64decode(hash_b64)
        obtido = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 310_000)
        return hmac.compare_digest(obtido, esperado)
    except (ValueError, TypeError):
        return False


def verificar_senha_login(senha: str, registro: dict | None) -> bool:
    armazenada = registro["senha_hash"] if registro else _HASH_SIMULADO
    return verificar_senha(senha, armazenada) and registro is not None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _derivar_csrf(token_sessao: str) -> str:
    # Determinístico a partir do token de sessão (secreto, httponly,
    # compartilhado por cookie entre todas as abas do navegador) em vez de um
    # valor aleatório girado a cada checagem: antes, abrir uma 2ª aba
    # sobrescrevia o único csrf_hash válido no banco e invalidava o token que
    # a 1ª aba já tinha em memória (cada aba guarda o csrf só localmente, sem
    # sincronizar entre si), quebrando a próxima ação nela com "validação de
    # segurança expirada". Derivar do token de sessão garante o mesmo valor
    # em qualquer aba, sem precisar de estado adicional nem rotação.
    return hmac.new(token_sessao.encode(), b"csrf", hashlib.sha256).hexdigest()


def contar_tentativas_invalidas(cursor, usuario: str, ip: str) -> int:
    cursor.execute(
        """SELECT COUNT(*) AS total FROM tentativas_login_aeri
        WHERE usuario=%s AND ip=%s AND sucesso=FALSE
        AND criada_em > NOW() - (%s * INTERVAL '1 minute')""",
        (usuario, ip, JANELA_TENTATIVAS_MINUTOS),
    )
    return cursor.fetchone()["total"]


def registrar_tentativa_cursor(cursor, usuario: str, ip: str, sucesso: bool) -> None:
    if sucesso:
        cursor.execute("DELETE FROM tentativas_login_aeri WHERE usuario=%s AND ip=%s", (usuario, ip))
    else:
        cursor.execute(
            "INSERT INTO tentativas_login_aeri (usuario, ip, sucesso) VALUES (%s, %s, FALSE)",
            (usuario, ip),
        )
    cursor.execute("DELETE FROM tentativas_login_aeri WHERE criada_em < NOW() - INTERVAL '2 days'")


def registrar_tentativa(usuario: str, ip: str, sucesso: bool) -> None:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            registrar_tentativa_cursor(cursor, usuario, ip, sucesso)
        conexao.commit()


def criar_sessao(usuario: str, request: Request) -> tuple[str, str]:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            token, csrf = criar_sessao_cursor(cursor, usuario, request)
        conexao.commit()
    return token, csrf


def criar_sessao_cursor(cursor, usuario: str, request: Request) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf = _derivar_csrf(token)
    agora = datetime.now(timezone.utc)
    cursor.execute("DELETE FROM sessoes_aeri WHERE expira_em < NOW() OR revogada_em IS NOT NULL")
    cursor.execute(
        """INSERT INTO sessoes_aeri
        (id, usuario, token_hash, csrf_hash, ip, user_agent, expira_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (uuid4(), usuario, _hash_token(token), _hash_token(csrf), ip_cliente(request),
         request.headers.get("user-agent", "")[:300], agora + timedelta(seconds=SESSAO_SEGUNDOS)),
    )
    return token, csrf


def _obter_sessao(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return None
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT s.*, u.*,
                COALESCE((
                    SELECT jsonb_object_agg(chave, TRUE)
                    FROM (
                        SELECT pp.permissao AS chave
                        FROM perfis_permissoes_aeri pp WHERE pp.perfil=u.perfil
                        UNION
                        SELECT up.permissao AS chave
                        FROM usuarios_permissoes_aeri up
                        WHERE up.usuario=u.usuario AND up.concedida=TRUE
                    ) permissoes_efetivas
                ), '{}'::jsonb) AS permissoes_relacionais
                FROM sessoes_aeri s JOIN usuarios_aeri u ON u.usuario=s.usuario
                WHERE s.token_hash=%s AND s.revogada_em IS NULL AND u.ativo=TRUE
                AND s.expira_em > NOW() AND s.ultimo_acesso > NOW() - (%s * INTERVAL '1 second')""",
                (_hash_token(token), INATIVIDADE_SEGUNDOS),
            )
            sessao = cursor.fetchone()
            if sessao and request.headers.get("x-aeri-background") != "1":
                # Requisições periódicas não são atividade humana. Além de
                # impedir a expiração real por inatividade, escrever em toda
                # consulta gerava contenção desnecessária no Postgres.
                cursor.execute(
                    """UPDATE sessoes_aeri SET ultimo_acesso=NOW()
                    WHERE id=%s AND ultimo_acesso < NOW() - INTERVAL '5 minutes'""",
                    (sessao["id"],),
                )
        conexao.commit()
    return sessao


def _sessao_da_requisicao(request: Request) -> dict | None:
    # proteger_csrf e usuario_atual precisam da mesma sessão numa mesma
    # requisição (a rota de escrita típica usa os dois). Sem esse
    # compartilhamento, cada um buscava a sessão do zero -- conexão nova,
    # SELECT com JOIN e UPDATE de último acesso, duas vezes -- dobrando o
    # custo de banco de toda ação de salvar/gravar do sistema.
    sessao = getattr(request.state, "sessao", None)
    if sessao is None:
        sessao = _obter_sessao(request)
        if sessao:
            request.state.sessao = sessao
    return sessao


def usuario_atual(request: Request) -> str:
    sessao = _sessao_da_requisicao(request)
    if not sessao:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    return sessao["usuario"]


def permissoes_sessao(sessao: dict) -> dict:
    if sessao["perfil"] in PERFIS_ADMINISTRATIVOS:
        return {chave: True for chave in PERMISSOES}
    relacionais = permissoes_relacionais_do_registro(sessao)
    if relacionais is not None:
        if sessao["perfil"] == "AUDITOR":
            relacionais = PERMISSOES_AUDITOR | (relacionais & PERMISSOES_OPCIONAIS_AUDITOR)
        return {chave: chave in relacionais for chave in PERMISSOES}
    if sessao["perfil"] == "AUDITOR":
        return {
            chave: (
                chave in PERMISSOES_AUDITOR
                or (
                    chave in PERMISSOES_OPCIONAIS_AUDITOR
                    and bool(sessao.get(COLUNAS_LEGADAS[chave]))
                )
            )
            for chave in PERMISSOES
        }
    return {chave: bool(sessao.get(coluna)) for chave, coluna in COLUNAS_LEGADAS.items()}


def exigir_perfis(*perfis: str):
    def verificar(request: Request, usuario: str = Depends(usuario_atual)) -> str:
        sessao = request.state.sessao
        if sessao["deve_trocar_senha"]:
            raise HTTPException(status_code=403, detail="Troque sua senha temporária para continuar.")
        if sessao["perfil"] not in perfis:
            raise HTTPException(status_code=403, detail="Você não possui permissão para esta operação.")
        return usuario
    return verificar


def exigir_permissao(permissao: str):
    if permissao not in PERMISSOES:
        raise RuntimeError(f"Permissão desconhecida: {permissao}")

    def verificar(request: Request, usuario: str = Depends(usuario_atual)) -> str:
        sessao = request.state.sessao
        if sessao["deve_trocar_senha"]:
            raise HTTPException(status_code=403, detail="Troque sua senha temporária para continuar.")
        if permissoes_sessao(sessao).get(permissao):
            return usuario
        raise HTTPException(status_code=403, detail="Você não possui permissão para esta operação.")

    return verificar


def proteger_csrf(request: Request) -> None:
    validar_origem(request)
    token_sessao = request.cookies.get(COOKIE_SESSAO, "")
    sessao = _sessao_da_requisicao(request)
    cabecalho = request.headers.get("x-csrf-token", "")
    if not sessao or not token_sessao or not cabecalho:
        raise HTTPException(status_code=403, detail="Validação de segurança expirada.")
    if not hmac.compare_digest(cabecalho, _derivar_csrf(token_sessao)):
        raise HTTPException(status_code=403, detail="Validação de segurança expirada.")


def csrf_atual(request: Request) -> str:
    sessao = getattr(request.state, "sessao", None)
    if not sessao:
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    return _derivar_csrf(request.cookies.get(COOKIE_SESSAO, ""))


def revogar_sessao(request: Request) -> None:
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE token_hash=%s", (_hash_token(token),))
        conexao.commit()
