"""Salão recreativo privado, isolado dos dados operacionais do AERI."""

import json
import hmac
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import proteger_csrf, usuario_atual, verificar_senha, hash_senha
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import ip_cliente


router = APIRouter(prefix="/api/jogos", tags=["jogos"], include_in_schema=False)

_LINHAS_VITORIA = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def _codigo_acesso_valido(informado: str) -> bool:
    configurado = os.getenv("AERI_JOGOS_SENHA", "")
    if not configurado:
        raise HTTPException(status_code=503, detail="Acesso reservado indisponível.")
    return hmac.compare_digest(informado.encode("utf-8"), configurado.encode("utf-8"))


def _sessao_id(request: Request) -> UUID:
    sessao = getattr(request.state, "sessao", None)
    if not sessao or not sessao.get("id"):
        raise HTTPException(status_code=401, detail="Faça login para continuar.")
    return sessao["id"]


def _limpar_expirados(cursor) -> None:
    cursor.execute(
        "UPDATE jogos_convites_aeri SET estado='EXPIRADO' "
        "WHERE estado='PENDENTE' AND expira_em <= NOW()"
    )
    cursor.execute(
        """UPDATE jogos_salas_aeri s SET estado='ABANDONADA', atualizado_em=NOW()
        WHERE s.estado='AGUARDANDO' AND NOT EXISTS (
            SELECT 1 FROM jogos_convites_aeri c WHERE c.sala_id=s.id
            AND c.estado='PENDENTE' AND c.expira_em > NOW()
        )"""
    )
    cursor.execute(
        "UPDATE jogos_salas_aeri SET estado='ABANDONADA', atualizado_em=NOW() "
        "WHERE estado IN ('AGUARDANDO','EM_JOGO') "
        "AND atualizado_em < NOW() - INTERVAL '2 hours'"
    )
    cursor.execute(
        "DELETE FROM jogos_tentativas_aeri WHERE criada_em < NOW() - INTERVAL '1 day'"
    )
    cursor.execute(
        "DELETE FROM jogos_salas_aeri WHERE estado IN ('FINALIZADA','ABANDONADA') "
        "AND atualizado_em < NOW() - INTERVAL '7 days'"
    )


def _exigir_acesso(request: Request, usuario: str = Depends(usuario_atual)) -> str:
    sessao_id = _sessao_id(request)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM jogos_acessos_aeri "
                "WHERE sessao_id=%s AND usuario=%s AND autorizado_ate > NOW()",
                (sessao_id, usuario),
            )
            permitido = cursor.fetchone()
    if not permitido:
        raise HTTPException(status_code=403, detail="Acesso adicional necessário.")
    return usuario


def _presencas(cursor, usuario: str) -> list[dict]:
    cursor.execute(
        """SELECT DISTINCT ON (a.usuario) a.usuario, u.nome
        FROM jogos_acessos_aeri a
        JOIN usuarios_aeri u ON u.usuario=a.usuario AND u.ativo=TRUE
        JOIN sessoes_aeri s ON s.id=a.sessao_id AND s.revogada_em IS NULL AND s.expira_em > NOW()
        WHERE a.presente_ate > NOW() AND a.autorizado_ate > NOW() AND a.usuario <> %s
        ORDER BY a.usuario, a.presente_ate DESC""",
        (usuario,),
    )
    return [{"usuario": item["usuario"], "nome": item.get("nome") or item["usuario"]}
            for item in cursor.fetchall()]


def _convites(cursor, usuario: str) -> list[dict]:
    cursor.execute(
        """SELECT c.id, c.sala_id, c.remetente, s.nome AS sala_nome,
        COALESCE(u.nome, c.remetente) AS remetente_nome, c.expira_em
        FROM jogos_convites_aeri c
        JOIN jogos_salas_aeri s ON s.id=c.sala_id
        LEFT JOIN usuarios_aeri u ON u.usuario=c.remetente
        WHERE c.destinatario=%s AND c.estado='PENDENTE' AND c.expira_em > NOW()
        AND s.estado='AGUARDANDO'
        ORDER BY c.criado_em DESC""",
        (usuario,),
    )
    return [{
        "id": str(item["id"]), "salaId": str(item["sala_id"]),
        "sala": item["sala_nome"], "remetente": item["remetente"],
        "remetenteNome": item["remetente_nome"], "expiraEm": item["expira_em"],
    } for item in cursor.fetchall()]


def _resultado_tabuleiro(tabuleiro: list[str]) -> str | None:
    for a, b, c in _LINHAS_VITORIA:
        if tabuleiro[a] and tabuleiro[a] == tabuleiro[b] == tabuleiro[c]:
            return tabuleiro[a]
    return "EMPATE" if all(tabuleiro) else None


def _sala_para_resposta(cursor, sala_id: UUID, usuario: str) -> dict:
    cursor.execute(
        """SELECT s.*, COALESCE(ux.nome,s.jogador_x) AS nome_x,
        COALESCE(uo.nome,s.jogador_o) AS nome_o
        FROM jogos_salas_aeri s
        LEFT JOIN usuarios_aeri ux ON ux.usuario=s.jogador_x
        LEFT JOIN usuarios_aeri uo ON uo.usuario=s.jogador_o
        WHERE s.id=%s AND %s IN (s.jogador_x, s.jogador_o)""",
        (sala_id, usuario),
    )
    sala = cursor.fetchone()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala não encontrada.")
    simbolo = "X" if sala["jogador_x"] == usuario else "O"
    return {
        "id": str(sala["id"]), "nome": sala["nome"], "estado": sala["estado"],
        "tabuleiro": sala["tabuleiro"], "vez": sala["vez"],
        "vencedor": sala.get("vencedor"), "simbolo": simbolo,
        "jogadorX": {"usuario": sala["jogador_x"], "nome": sala["nome_x"]},
        "jogadorO": ({"usuario": sala["jogador_o"], "nome": sala["nome_o"]}
                      if sala.get("jogador_o") else None),
        "versao": sala["versao"],
    }


def _sala_atual(cursor, usuario: str) -> dict | None:
    cursor.execute(
        """SELECT id FROM jogos_salas_aeri
        WHERE estado IN ('AGUARDANDO','EM_JOGO') AND %s IN (jogador_x,jogador_o)
        ORDER BY atualizado_em DESC LIMIT 1""",
        (usuario,),
    )
    atual = cursor.fetchone()
    return _sala_para_resposta(cursor, atual["id"], usuario) if atual else None


@router.post("/entrar", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def entrar(dados: dict, request: Request, usuario: str = Depends(usuario_atual)):
    senha = str(dados.get("senha") or "")[:64]
    sessao_id = _sessao_id(request)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            _limpar_expirados(cursor)
            cursor.execute(
                """SELECT COUNT(*) AS total FROM jogos_tentativas_aeri
                WHERE sessao_id=%s AND sucesso=FALSE
                AND criada_em > NOW() - INTERVAL '15 minutes'""",
                (sessao_id,),
            )
            if cursor.fetchone()["total"] >= 5:
                conexao.commit()
                raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde 15 minutos.")
            valido = _codigo_acesso_valido(senha)
            cursor.execute(
                "INSERT INTO jogos_tentativas_aeri (sessao_id,ip,sucesso) VALUES (%s,%s,%s)",
                (sessao_id, ip_cliente(request), valido),
            )
            if not valido:
                conexao.commit()
                raise HTTPException(status_code=422, detail="Código inválido.")
            cursor.execute(
                "DELETE FROM jogos_tentativas_aeri WHERE sessao_id=%s AND sucesso=FALSE",
                (sessao_id,),
            )
            cursor.execute(
                """INSERT INTO jogos_acessos_aeri
                (sessao_id,usuario,autorizado_ate,presente_ate,atualizado_em)
                VALUES (%s,%s,NOW()+INTERVAL '8 hours',NOW()+INTERVAL '30 seconds',NOW())
                ON CONFLICT (sessao_id) DO UPDATE SET usuario=EXCLUDED.usuario,
                autorizado_ate=EXCLUDED.autorizado_ate,
                presente_ate=EXCLUDED.presente_ate, atualizado_em=NOW()""",
                (sessao_id, usuario),
            )
        conexao.commit()
    return {"autorizado": True}


@router.post("/presenca", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def presenca(request: Request, usuario: str = Depends(_exigir_acesso)):
    sessao_id = _sessao_id(request)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            _limpar_expirados(cursor)
            cursor.execute(
                """UPDATE jogos_acessos_aeri
                SET presente_ate=NOW()+INTERVAL '30 seconds', atualizado_em=NOW()
                WHERE sessao_id=%s AND autorizado_ate > NOW()""",
                (sessao_id,),
            )
            online = _presencas(cursor, usuario)
            convites = _convites(cursor, usuario)
            sala_atual = _sala_atual(cursor, usuario)
        conexao.commit()
    return {"online": online, "convites": convites, "salaAtual": sala_atual}


@router.post("/sair", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def sair(request: Request, usuario: str = Depends(_exigir_acesso)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE jogos_acessos_aeri SET presente_ate=NOW() WHERE sessao_id=%s AND usuario=%s",
                (_sessao_id(request), usuario),
            )
        conexao.commit()
    return {"ok": True}


@router.post("/salas", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def criar_sala(dados: dict, usuario: str = Depends(_exigir_acesso)):
    nome = " ".join(str(dados.get("nome") or "").split())[:50]
    senha = str(dados.get("senha") or "")[:64]
    convidado = str(dados.get("convidado") or "").strip().upper()[:80]
    if not nome or len(senha) < 4 or not convidado or convidado == usuario:
        raise HTTPException(status_code=400, detail="Informe sala, senha e jogador convidado.")
    sala_id, convite_id = uuid4(), uuid4()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            _limpar_expirados(cursor)
            cursor.execute(
                """SELECT 1 FROM jogos_acessos_aeri a
                JOIN usuarios_aeri u ON u.usuario=a.usuario AND u.ativo=TRUE
                WHERE a.usuario=%s AND a.presente_ate > NOW() AND a.autorizado_ate > NOW()
                LIMIT 1""",
                (convidado,),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=409, detail="Essa pessoa não está mais no salão.")
            cursor.execute(
                """UPDATE jogos_salas_aeri SET estado='ABANDONADA', atualizado_em=NOW()
                WHERE estado IN ('AGUARDANDO','EM_JOGO') AND %s IN (jogador_x,jogador_o)""",
                (usuario,),
            )
            cursor.execute(
                """INSERT INTO jogos_salas_aeri
                (id,nome,senha_hash,criador,jogador_x) VALUES (%s,%s,%s,%s,%s)""",
                (sala_id, nome, hash_senha(senha), usuario, usuario),
            )
            cursor.execute(
                """INSERT INTO jogos_convites_aeri
                (id,sala_id,remetente,destinatario) VALUES (%s,%s,%s,%s)""",
                (convite_id, sala_id, usuario, convidado),
            )
        conexao.commit()
    return {"salaId": str(sala_id), "conviteId": str(convite_id)}


@router.post("/convites/{convite_id}/aceitar", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def aceitar_convite(convite_id: UUID, dados: dict, usuario: str = Depends(_exigir_acesso)):
    senha = str(dados.get("senha") or "")[:64]
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            _limpar_expirados(cursor)
            cursor.execute(
                """SELECT c.*,s.senha_hash,s.estado AS sala_estado,s.jogador_o
                FROM jogos_convites_aeri c JOIN jogos_salas_aeri s ON s.id=c.sala_id
                WHERE c.id=%s AND c.destinatario=%s FOR UPDATE OF c,s""",
                (convite_id, usuario),
            )
            convite = cursor.fetchone()
            if not convite or convite["estado"] != "PENDENTE" or convite["sala_estado"] != "AGUARDANDO":
                raise HTTPException(status_code=409, detail="O convite não está mais disponível.")
            if convite.get("jogador_o") or not verificar_senha(senha, convite["senha_hash"]):
                raise HTTPException(status_code=422, detail="Senha da sala inválida.")
            cursor.execute(
                """UPDATE jogos_salas_aeri SET jogador_o=%s,estado='EM_JOGO',
                atualizado_em=NOW(),versao=versao+1 WHERE id=%s""",
                (usuario, convite["sala_id"]),
            )
            cursor.execute("UPDATE jogos_convites_aeri SET estado='ACEITO' WHERE id=%s", (convite_id,))
            sala = _sala_para_resposta(cursor, convite["sala_id"], usuario)
        conexao.commit()
    return sala


@router.post("/convites/{convite_id}/recusar", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def recusar_convite(convite_id: UUID, usuario: str = Depends(_exigir_acesso)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE jogos_convites_aeri SET estado='RECUSADO'
                WHERE id=%s AND destinatario=%s AND estado='PENDENTE' RETURNING sala_id""",
                (convite_id, usuario),
            )
            recusado = cursor.fetchone()
            if not recusado:
                raise HTTPException(status_code=404, detail="Convite não encontrado.")
        conexao.commit()
    return {"ok": True}


@router.get("/salas/{sala_id}", dependencies=[Depends(preparar_banco)])
def consultar_sala(sala_id: UUID, usuario: str = Depends(_exigir_acesso)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            return _sala_para_resposta(cursor, sala_id, usuario)


@router.post("/salas/{sala_id}/jogar", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def jogar(sala_id: UUID, dados: dict, usuario: str = Depends(_exigir_acesso)):
    try:
        indice = int(dados.get("indice"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Jogada inválida.")
    if indice < 0 or indice > 8:
        raise HTTPException(status_code=400, detail="Jogada inválida.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT * FROM jogos_salas_aeri WHERE id=%s FOR UPDATE", (sala_id,))
            sala = cursor.fetchone()
            if not sala or usuario not in (sala["jogador_x"], sala.get("jogador_o")):
                raise HTTPException(status_code=404, detail="Sala não encontrada.")
            simbolo = "X" if usuario == sala["jogador_x"] else "O"
            tabuleiro = list(sala["tabuleiro"] or [])
            if sala["estado"] != "EM_JOGO" or sala["vez"] != simbolo:
                raise HTTPException(status_code=409, detail="Aguarde a sua vez.")
            if len(tabuleiro) != 9 or tabuleiro[indice]:
                raise HTTPException(status_code=409, detail="Essa casa não está disponível.")
            tabuleiro[indice] = simbolo
            vencedor = _resultado_tabuleiro(tabuleiro)
            estado = "FINALIZADA" if vencedor else "EM_JOGO"
            proxima_vez = "O" if simbolo == "X" else "X"
            cursor.execute(
                """UPDATE jogos_salas_aeri SET tabuleiro=%s::jsonb,vez=%s,vencedor=%s,
                estado=%s,versao=versao+1,atualizado_em=NOW() WHERE id=%s""",
                (json.dumps(tabuleiro), proxima_vez, vencedor, estado, sala_id),
            )
            resposta = _sala_para_resposta(cursor, sala_id, usuario)
        conexao.commit()
    return resposta


@router.post("/salas/{sala_id}/reiniciar", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def reiniciar(sala_id: UUID, usuario: str = Depends(_exigir_acesso)):
    vazio = '["", "", "", "", "", "", "", "", ""]'
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE jogos_salas_aeri SET tabuleiro=%s::jsonb,vez='X',vencedor=NULL,
                estado='EM_JOGO',versao=versao+1,atualizado_em=NOW()
                WHERE id=%s AND jogador_o IS NOT NULL AND %s IN (jogador_x,jogador_o)
                RETURNING id""",
                (vazio, sala_id, usuario),
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Sala não encontrada.")
            resposta = _sala_para_resposta(cursor, sala_id, usuario)
        conexao.commit()
    return resposta


@router.post("/salas/{sala_id}/abandonar", dependencies=[Depends(preparar_banco), Depends(proteger_csrf)])
def abandonar(sala_id: UUID, usuario: str = Depends(_exigir_acesso)):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE jogos_salas_aeri SET estado='ABANDONADA',atualizado_em=NOW(),
                versao=versao+1 WHERE id=%s AND %s IN (jogador_x,jogador_o)""",
                (sala_id, usuario),
            )
        conexao.commit()
    return {"ok": True}
