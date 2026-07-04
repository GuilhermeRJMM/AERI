import re

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.errors import UniqueViolation

from backend.app.autenticacao import (
    exigir_perfis,
    hash_senha,
    proteger_csrf,
    senha_forte,
    usuario_atual,
    verificar_senha,
)
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria


PERFIS = {"ADMIN", "OPERADOR", "CONSULTA"}
router = APIRouter(prefix="/api/usuarios", tags=["usuários"], dependencies=[Depends(preparar_banco)])


def _usuario_json(item: dict) -> dict:
    return {
        "usuario": item["usuario"], "nome": item["nome"], "perfil": item["perfil"],
        "ativo": item["ativo"], "deveTrocarSenha": item["deve_trocar_senha"],
        "criadoEm": item["criado_em"].isoformat(),
    }


def _validar_usuario(dados: dict, exigir_senha: bool = True) -> tuple[str, str, str, str]:
    usuario = str(dados.get("usuario", "")).strip().upper()
    nome = str(dados.get("nome", "")).strip()
    perfil = str(dados.get("perfil", "")).strip().upper()
    senha = str(dados.get("senha", ""))
    if not re.fullmatch(r"[A-Z0-9._-]{3,40}", usuario):
        raise HTTPException(status_code=422, detail="Use de 3 a 40 letras, números, ponto, hífen ou sublinhado.")
    if not nome or len(nome) > 160 or perfil not in PERFIS:
        raise HTTPException(status_code=422, detail="Informe nome e perfil válidos.")
    if exigir_senha and not senha_forte(senha):
        raise HTTPException(status_code=422, detail="A senha precisa ter 14 caracteres, maiúscula, minúscula, número e símbolo.")
    return usuario, nome, perfil, senha


@router.get("")
def listar_usuarios(_admin: str = Depends(exigir_perfis("ADMIN"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM usuarios_aeri ORDER BY ativo DESC, nome, usuario")
            return [_usuario_json(item) for item in cursor.fetchall()]


@router.get("/auditoria")
def listar_auditoria(_admin: str = Depends(exigir_perfis("ADMIN"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT usuario, acao, recurso, resultado, ip, criada_em
                FROM auditoria_aeri ORDER BY criada_em DESC LIMIT 300"""
            )
            return [
                {**item, "criada_em": item["criada_em"].isoformat()}
                for item in cursor.fetchall()
            ]


@router.post("", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_usuario(dados: dict, request: Request, admin: str = Depends(exigir_perfis("ADMIN"))):
    usuario, nome, perfil, senha = _validar_usuario(dados)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO usuarios_aeri
                    (usuario, nome, perfil, senha_hash, deve_trocar_senha)
                    VALUES (%s, %s, %s, %s, TRUE) RETURNING *""",
                    (usuario, nome, perfil, hash_senha(senha)),
                )
                item = cursor.fetchone()
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este usuário já existe.") from exc
    registrar_auditoria(request, "criar_usuario", "sucesso", admin, usuario, {"perfil": perfil})
    return _usuario_json(item)


@router.put("/{usuario_alvo}", dependencies=[Depends(proteger_csrf)])
def atualizar_usuario(usuario_alvo: str, dados: dict, request: Request, admin: str = Depends(exigir_perfis("ADMIN"))):
    usuario_alvo = usuario_alvo.upper()
    _, nome, perfil, _ = _validar_usuario({**dados, "usuario": usuario_alvo}, exigir_senha=False)
    ativo = bool(dados.get("ativo", True))
    if usuario_alvo == admin and (not ativo or perfil != "ADMIN"):
        raise HTTPException(status_code=422, detail="O administrador não pode remover o próprio acesso total.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE usuarios_aeri SET nome=%s, perfil=%s, ativo=%s, atualizado_em=NOW()
                WHERE usuario=%s RETURNING *""", (nome, perfil, ativo, usuario_alvo),
            )
            item = cursor.fetchone()
            if item and not ativo:
                cursor.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE usuario=%s", (usuario_alvo,))
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    registrar_auditoria(request, "atualizar_usuario", "sucesso", admin, usuario_alvo, {"perfil": perfil, "ativo": ativo})
    return _usuario_json(item)


@router.post("/{usuario_alvo}/redefinir-senha", dependencies=[Depends(proteger_csrf)])
def redefinir_senha(usuario_alvo: str, dados: dict, request: Request, admin: str = Depends(exigir_perfis("ADMIN"))):
    senha = str(dados.get("senha", ""))
    if not senha_forte(senha):
        raise HTTPException(status_code=422, detail="A senha precisa ter 14 caracteres, maiúscula, minúscula, número e símbolo.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE usuarios_aeri SET senha_hash=%s, deve_trocar_senha=TRUE, atualizado_em=NOW()
                WHERE usuario=%s RETURNING usuario""", (hash_senha(senha), usuario_alvo.upper()),
            )
            item = cursor.fetchone()
            cursor.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE usuario=%s", (usuario_alvo.upper(),))
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    registrar_auditoria(request, "redefinir_senha", "sucesso", admin, usuario_alvo.upper())
    return {"ok": True}


@router.post("/minha-senha/trocar", dependencies=[Depends(usuario_atual), Depends(proteger_csrf)])
def trocar_minha_senha(dados: dict, request: Request):
    usuario = request.state.sessao["usuario"]
    atual = str(dados.get("senhaAtual", ""))
    nova = str(dados.get("novaSenha", ""))
    if not senha_forte(nova):
        raise HTTPException(status_code=422, detail="A nova senha precisa ter 14 caracteres, maiúscula, minúscula, número e símbolo.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT senha_hash FROM usuarios_aeri WHERE usuario=%s", (usuario,))
            registro = cursor.fetchone()
            if not registro or not verificar_senha(atual, registro["senha_hash"]):
                raise HTTPException(status_code=401, detail="Senha atual inválida.")
            cursor.execute(
                """UPDATE usuarios_aeri SET senha_hash=%s, deve_trocar_senha=FALSE, atualizado_em=NOW()
                WHERE usuario=%s""", (hash_senha(nova), usuario),
            )
        conexao.commit()
    registrar_auditoria(request, "trocar_senha", "sucesso", usuario)
    return {"ok": True}
