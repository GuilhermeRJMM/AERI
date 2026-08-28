import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation

from backend.app.autenticacao import (
    PERMISSOES,
    PERMISSOES_AUDITOR,
    PERMISSOES_OPCIONAIS_AUDITOR,
    PERFIS_ADMINISTRATIVOS,
    exigir_perfis,
    hash_senha,
    permissoes_sessao,
    proteger_csrf,
    senha_forte,
    usuario_atual,
    verificar_senha,
)
from backend.app.database import conectar, preparar_banco
from backend.app.permissoes import (
    catalogo_publico,
    definir_permissao_usuario_cursor,
    selecionar_usuarios_com_permissoes,
    substituir_permissoes_usuario_cursor,
)
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.seguranca_mfa import cifrar_segredo, novo_segredo, uri_totp, validar_totp


PERFIS = {"ADMIN", "SUBSTITUTO", "AUDITOR", "SUPERVISOR", "CONFERENTE", "PRODUTOR"}
router = APIRouter(prefix="/api/usuarios", tags=["usuários"], dependencies=[Depends(preparar_banco)])


def _usuario_json(item: dict) -> dict:
    herdadas = item.get("permissoes_perfil") or {}
    individuais = item.get("permissoes_usuario") or {}
    return {
        "usuario": item["usuario"], "nome": item["nome"], "perfil": item["perfil"], "cargo": item["perfil"],
        "ativo": item["ativo"], "deveTrocarSenha": item["deve_trocar_senha"],
        "criadoEm": item["criado_em"].isoformat(),
        "permissoes": permissoes_sessao(item),
        "origensPermissoes": {"herdadas": herdadas, "individuais": individuais},
        "senhaTemporariaExpiraEm": (
            item.get("senha_temporaria_expira_em").isoformat()
            if item.get("senha_temporaria_expira_em") else None
        ),
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
        raise HTTPException(status_code=422, detail="A senha precisa ter 10 caracteres, maiúscula, número e símbolo.")
    return usuario, nome, perfil, senha


def _validar_permissoes(dados: dict, perfil: str) -> dict:
    if perfil in PERFIS_ADMINISTRATIVOS:
        return {coluna: True for coluna in PERMISSOES.values()}
    permissoes = dados.get("permissoes") or {}
    if perfil == "AUDITOR":
        return {
            coluna: (
                chave in PERMISSOES_AUDITOR
                or (
                    chave in PERMISSOES_OPCIONAIS_AUDITOR
                    and bool(permissoes.get(chave, False))
                )
            )
            for chave, coluna in PERMISSOES.items()
        }
    return {
        coluna: bool(permissoes.get(chave, False))
        for chave, coluna in PERMISSOES.items()
    }


def _permissoes_por_chave(dados: dict, perfil: str) -> dict:
    validadas = _validar_permissoes(dados, perfil)
    return {chave: validadas[coluna] for chave, coluna in PERMISSOES.items()}


def _buscar_usuario_cursor(cursor, usuario: str) -> dict | None:
    cursor.execute(
        selecionar_usuarios_com_permissoes("WHERE u.usuario=%s", ordem=""),
        (usuario,),
    )
    return cursor.fetchone()


@router.get("")
def listar_usuarios(_admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(selecionar_usuarios_com_permissoes())
            return [_usuario_json(item) for item in cursor.fetchall()]


@router.get("/permissoes/catalogo")
def listar_catalogo_permissoes(_admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    return catalogo_publico()


@router.get("/auditoria")
def listar_auditoria(_admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
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
    permissoes = _permissoes_por_chave(dados, perfil)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO usuarios_aeri
                    (usuario, nome, perfil, senha_hash, deve_trocar_senha)
                    VALUES (%s, %s, %s, %s, TRUE) RETURNING usuario""",
                    (usuario, nome, perfil, hash_senha(senha)),
                )
                cursor.execute(
                    "UPDATE usuarios_aeri SET senha_temporaria_expira_em=NOW()+INTERVAL '24 hours' WHERE usuario=%s",
                    (usuario,),
                )
                cursor.fetchone()
                substituir_permissoes_usuario_cursor(cursor, usuario, perfil, permissoes)
                item = _buscar_usuario_cursor(cursor, usuario)
                registrar_auditoria_cursor(cursor, request, "criar_usuario", "sucesso", admin, usuario, {"perfil": perfil})
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este usuário já existe.") from exc
    return _usuario_json(item)


@router.put("/{usuario_alvo}", dependencies=[Depends(proteger_csrf)])
def atualizar_usuario(usuario_alvo: str, dados: dict, request: Request, admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    usuario_alvo = usuario_alvo.upper()
    _, nome, perfil, _ = _validar_usuario({**dados, "usuario": usuario_alvo}, exigir_senha=False)
    perfil_editor = request.state.sessao["perfil"]
    if perfil_editor != "ADMIN" and perfil in PERFIS_ADMINISTRATIVOS:
        raise HTTPException(status_code=403, detail="Somente ADM pode atribuir cargo administrativo.")
    permissoes = _permissoes_por_chave(dados, perfil)
    ativo = bool(dados.get("ativo", True))
    if usuario_alvo == admin and (not ativo or perfil != perfil_editor):
        raise HTTPException(status_code=422, detail="O administrador não pode remover o próprio acesso total.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT perfil, ativo FROM usuarios_aeri WHERE usuario=%s", (usuario_alvo,))
            anterior_usuario = cursor.fetchone()
            if request.state.sessao["perfil"] != "ADMIN":
                cursor.execute("SELECT perfil FROM usuarios_aeri WHERE usuario=%s", (usuario_alvo.upper(),))
                existente = cursor.fetchone()
                if existente and existente["perfil"] in PERFIS_ADMINISTRATIVOS:
                    raise HTTPException(status_code=403, detail="Somente ADM pode alterar cargo administrativo.")
            cursor.execute(
                """UPDATE usuarios_aeri SET nome=%s, perfil=%s, ativo=%s,
                atualizado_em=NOW() WHERE usuario=%s RETURNING usuario""",
                (nome, perfil, ativo, usuario_alvo),
            )
            atualizado = cursor.fetchone()
            if atualizado:
                substituir_permissoes_usuario_cursor(cursor, usuario_alvo, perfil, permissoes)
            item = _buscar_usuario_cursor(cursor, usuario_alvo) if atualizado else None
            if item and not ativo:
                cursor.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE usuario=%s", (usuario_alvo,))
            if item:
                registrar_auditoria_cursor(
                    cursor, request, "atualizar_usuario", "sucesso", admin, usuario_alvo,
                    {"antes": {"perfil": anterior_usuario["perfil"] if anterior_usuario else None,
                               "ativo": anterior_usuario["ativo"] if anterior_usuario else None},
                     "depois": {"perfil": perfil, "ativo": ativo, "permissoes": sorted(k for k,v in permissoes.items() if v)}},
                )
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return _usuario_json(item)


@router.patch("/{usuario_alvo}/permissoes/{permissao}", dependencies=[Depends(proteger_csrf)])
def atualizar_permissao_usuario(
    usuario_alvo: str,
    permissao: str,
    dados: dict,
    request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    usuario_alvo = usuario_alvo.upper()
    if permissao not in PERMISSOES:
        raise HTTPException(status_code=404, detail="Permissão desconhecida.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT perfil FROM usuarios_aeri WHERE usuario=%s", (usuario_alvo,))
            existente = cursor.fetchone()
            if not existente:
                raise HTTPException(status_code=404, detail="Usuário não encontrado.")
            perfil = existente["perfil"]
            if perfil in PERFIS_ADMINISTRATIVOS:
                raise HTTPException(status_code=422, detail="Cargos administrativos possuem acesso integral.")
            if perfil == "AUDITOR" and permissao not in PERMISSOES_OPCIONAIS_AUDITOR:
                raise HTTPException(status_code=422, detail="Esta atribuição é fixa ou indisponível para o Auditor.")
            concedida = bool(dados.get("concedida"))
            definir_permissao_usuario_cursor(cursor, usuario_alvo, permissao, concedida)
            item = _buscar_usuario_cursor(cursor, usuario_alvo)
            registrar_auditoria_cursor(
                cursor, request, "alterar_permissao", "sucesso", admin,
                usuario_alvo, {"antes": {"concedida": not concedida},
                                "depois": {"permissao": permissao, "concedida": concedida}},
            )
        conexao.commit()
    return _usuario_json(item)


@router.post("/{usuario_alvo}/redefinir-senha", dependencies=[Depends(proteger_csrf)])
def redefinir_senha(usuario_alvo: str, dados: dict, request: Request, admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    senha = str(dados.get("senha", ""))
    if not senha_forte(senha):
        raise HTTPException(status_code=422, detail="A senha precisa ter 10 caracteres, maiúscula, número e símbolo.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if request.state.sessao["perfil"] != "ADMIN":
                cursor.execute("SELECT perfil FROM usuarios_aeri WHERE usuario=%s", (usuario_alvo.upper(),))
                existente = cursor.fetchone()
                if existente and existente["perfil"] in PERFIS_ADMINISTRATIVOS:
                    raise HTTPException(status_code=403, detail="Somente ADM pode redefinir senha de cargo administrativo.")
            cursor.execute(
                """UPDATE usuarios_aeri SET senha_hash=%s, deve_trocar_senha=TRUE,
                senha_temporaria_expira_em=NOW()+INTERVAL '24 hours', atualizado_em=NOW()
                WHERE usuario=%s RETURNING usuario""", (hash_senha(senha), usuario_alvo.upper()),
            )
            item = cursor.fetchone()
            cursor.execute("UPDATE sessoes_aeri SET revogada_em=NOW() WHERE usuario=%s", (usuario_alvo.upper(),))
            if item:
                registrar_auditoria_cursor(
                    cursor, request, "redefinir_senha", "sucesso", admin,
                    usuario_alvo.upper())
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"ok": True}


@router.post("/minha-senha/trocar", dependencies=[Depends(usuario_atual), Depends(proteger_csrf)])
def trocar_minha_senha(dados: dict, request: Request):
    usuario = request.state.sessao["usuario"]
    atual = str(dados.get("senhaAtual", ""))
    nova = str(dados.get("novaSenha", ""))
    if not senha_forte(nova):
        raise HTTPException(status_code=422, detail="A nova senha precisa ter 10 caracteres, maiúscula, número e símbolo.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT senha_hash FROM usuarios_aeri WHERE usuario=%s", (usuario,))
            registro = cursor.fetchone()
            if not registro or not verificar_senha(atual, registro["senha_hash"]):
                # 422 e não 401: o cliente trata qualquer 401 como sessão
                # expirada e joga o usuário de volta para a tela de login.
                # Errar a senha atual não tem nada a ver com a sessão -- ela
                # segue válida --, e devolver 401 aqui expulsava quem só
                # tinha digitado errado, ainda por cima com a mensagem
                # trocada ("sua sessão expirou").
                raise HTTPException(status_code=422, detail="Senha atual inválida.")
            cursor.execute(
                """UPDATE usuarios_aeri SET senha_hash=%s, deve_trocar_senha=FALSE,
                senha_temporaria_expira_em=NULL, atualizado_em=NOW()
                WHERE usuario=%s""", (hash_senha(nova), usuario),
            )
            # Derruba as demais sessões (ex.: uma sessão roubada em outro
            # dispositivo) sem encerrar a sessão atual que acabou de trocar
            # a senha — ao contrário da redefinição feita por um ADM, aqui
            # o próprio usuário ainda está usando a sessão em uso.
            cursor.execute(
                "UPDATE sessoes_aeri SET revogada_em=NOW() WHERE usuario=%s AND id<>%s",
                (usuario, request.state.sessao["id"]),
            )
            registrar_auditoria_cursor(cursor, request, "trocar_senha", "sucesso", usuario)
        conexao.commit()
    return {"ok": True}


@router.get("/{usuario_alvo}/sessoes")
def listar_sessoes_usuario(
    usuario_alvo: str,
    _admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, ip, user_agent, criada_em, ultimo_acesso, expira_em, revogada_em
                FROM sessoes_aeri WHERE usuario=%s ORDER BY criada_em DESC LIMIT 50""",
                (usuario_alvo.upper(),),
            )
            return [{
                **item, "id": str(item["id"]),
                **{campo: item[campo].isoformat() if item[campo] else None
                   for campo in ("criada_em", "ultimo_acesso", "expira_em", "revogada_em")},
            } for item in cursor.fetchall()]


@router.delete("/{usuario_alvo}/sessoes/{sessao_id}", status_code=204, dependencies=[Depends(proteger_csrf)])
def revogar_sessao_usuario(
    usuario_alvo: str, sessao_id: UUID, request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE sessoes_aeri SET revogada_em=NOW() WHERE usuario=%s AND id=%s AND revogada_em IS NULL",
                (usuario_alvo.upper(), sessao_id),
            )
            removidos = cursor.rowcount
            if removidos:
                registrar_auditoria_cursor(cursor, request, "revogar_sessao", "sucesso", admin, usuario_alvo.upper(), {"sessao": str(sessao_id)})
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Sessão ativa não encontrada.")
    return Response(status_code=204)


@router.post("/minha-seguranca/mfa/iniciar", dependencies=[Depends(usuario_atual), Depends(proteger_csrf)])
def iniciar_mfa(request: Request):
    usuario = request.state.sessao["usuario"]
    if request.state.sessao["perfil"] not in PERFIS_ADMINISTRATIVOS:
        raise HTTPException(status_code=403, detail="MFA está disponível para cargos administrativos.")
    try:
        segredo = novo_segredo()
        cifrado = cifrar_segredo(segredo)
    except RuntimeError as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios_aeri SET mfa_segredo_criptografado=%s, mfa_ativo=FALSE WHERE usuario=%s",
                (cifrado, usuario),
            )
            registrar_auditoria_cursor(cursor, request, "iniciar_mfa", "sucesso", usuario)
        conexao.commit()
    return {"segredo": segredo, "uri": uri_totp(usuario, segredo)}


@router.post("/minha-seguranca/mfa/confirmar", dependencies=[Depends(usuario_atual), Depends(proteger_csrf)])
def confirmar_mfa(dados: dict, request: Request):
    usuario = request.state.sessao["usuario"]
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT mfa_segredo_criptografado FROM usuarios_aeri WHERE usuario=%s", (usuario,))
            item = cursor.fetchone()
            if not item or not item["mfa_segredo_criptografado"]:
                raise HTTPException(status_code=409, detail="Inicie a configuração MFA primeiro.")
            from backend.app.seguranca_mfa import decifrar_segredo
            if not validar_totp(decifrar_segredo(item["mfa_segredo_criptografado"]), dados.get("codigo")):
                raise HTTPException(status_code=422, detail="Código MFA inválido.")
            cursor.execute("UPDATE usuarios_aeri SET mfa_ativo=TRUE WHERE usuario=%s", (usuario,))
            registrar_auditoria_cursor(cursor, request, "ativar_mfa", "sucesso", usuario)
        conexao.commit()
    return {"ok": True}


@router.delete("/{usuario_alvo}/mfa", status_code=204, dependencies=[Depends(proteger_csrf)])
def redefinir_mfa_usuario(
    usuario_alvo: str, request: Request,
    admin: str = Depends(exigir_perfis("ADMIN")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios_aeri SET mfa_ativo=FALSE, mfa_segredo_criptografado=NULL WHERE usuario=%s",
                (usuario_alvo.upper(),),
            )
            alterados = cursor.rowcount
            registrar_auditoria_cursor(cursor, request, "redefinir_mfa", "sucesso", admin, usuario_alvo.upper())
        conexao.commit()
    if not alterados:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return Response(status_code=204)
