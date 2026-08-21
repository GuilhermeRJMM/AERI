import json
import logging
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from vercel.oidc import (
    VercelOidcTokenError,
    VercelOidcVerificationError,
    get_vercel_oidc_token,
    set_headers as definir_cabecalhos_oidc,
    verify_vercel_oidc_token,
)

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.tri7 import (
    ConfiguracaoTri7Invalida,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    cliente_tri7,
    normalizar_numero_matricula,
)
from backend.app.servicos.aprendizado_regras import (
    validar_id_regra,
    validar_sugestao_aprendizado,
)
from backend.app.servicos.fontes_juridicas import (
    agente_juridico_configurado,
    buscar_trechos_cursor,
    executar_agente_juridico,
    hash_base_juridica_cursor,
    importar_lote_juridico_cursor,
    limite_agente_juridico_diario,
    salvar_analise_juridica_cursor,
)


router = APIRouter(tags=["analisador"], dependencies=[Depends(preparar_banco)])
logger = logging.getLogger("aeri.analisador")
DOMINIOS_DIVERGENCIA = {"ONUS", "CADEIA", "IMOVEL", "SITUACAO"}


def _regras_aprovadas() -> list[dict]:
    """Compatibilidade do endpoint antigo, sem alterar o motor oficial.

    A tela de aprendizado foi retirada e as regras cadastradas ali eram
    aplicadas somente no Analisador, mas não em Buscas, Auditoria ou MAPA-ONR.
    Isso permitia resultados diferentes para a mesma matrícula. O histórico
    permanece no banco para auditoria, porém nenhuma regra dinâmica interfere
    no analisador determinístico.
    """
    return []


def _regra_json(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "expressao": item["expressao"],
        "categoria": item["categoria"],
        "impacta_resultado": item["impacta_resultado"],
        "tipo_onus": item["tipo_onus"] or None,
        "justificativa": item["justificativa"],
        "status": item["status"],
        "votos": item["votos"],
        "criado_por": item["criado_por"],
        "aprovado_por": item["aprovado_por"],
        "criado_em": item["criado_em"].isoformat(),
        "atualizado_em": item["atualizado_em"].isoformat(),
        "aprovado_em": item["aprovado_em"].isoformat() if item["aprovado_em"] else None,
    }


def _validar_feedback(dados: dict) -> dict:
    try:
        numero = normalizar_numero_matricula(dados.get("numero_matricula"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    avaliacao = str(dados.get("avaliacao", "")).strip().upper()
    if avaliacao not in {"CORRETO", "REVISAR"}:
        raise HTTPException(status_code=422, detail="Avaliação inválida.")
    hash_resultado = str(dados.get("resultado_hash", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", hash_resultado):
        raise HTTPException(status_code=422, detail="Identificador do resultado inválido.")
    dominios = sorted({str(item).strip().upper() for item in dados.get("dominios", [])})
    if not set(dominios).issubset(DOMINIOS_DIVERGENCIA):
        raise HTTPException(status_code=422, detail="Domínio de revisão inválido.")
    if avaliacao == "REVISAR" and not dominios:
        raise HTTPException(status_code=422, detail="Informe ao menos uma parte que precisa de revisão.")
    comentario = str(dados.get("comentario", "")).strip()
    if len(comentario) > 1000:
        raise HTTPException(status_code=422, detail="Comentário excede 1.000 caracteres.")
    resumo_recebido = dados.get("resumo") if isinstance(dados.get("resumo"), dict) else {}
    try:
        total_atos = max(0, min(int(resumo_recebido.get("total_atos", 0) or 0), 10000))
        total_proprietarios = max(0, min(int(resumo_recebido.get("total_proprietarios", 0) or 0), 10000))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Resumo do resultado inválido.") from exc
    resumo = {
        "resultado": str(resumo_recebido.get("resultado", ""))[:80],
        "situacao": str(resumo_recebido.get("situacao", ""))[:30],
        "total_atos": total_atos,
        "total_proprietarios": total_proprietarios,
    }
    return {
        "numero": numero,
        "avaliacao": avaliacao,
        "resultado_hash": hash_resultado,
        "dominios": dominios,
        "comentario": comentario,
        "motor_versao": str(dados.get("motor_versao", "desconhecida"))[:30],
        "resumo": resumo,
    }


def _divergencia_json(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "numero_matricula": item["numero_matricula"],
        "motor_versao": item["motor_versao"],
        "avaliacao": item["avaliacao"],
        "dominios": item["dominios"],
        "comentario": item["comentario"],
        "resumo": item["resumo"],
        "status": item["status"],
        "criado_por": item["criado_por"],
        "revisado_por": item["revisado_por"],
        "resolucao": item["resolucao"],
        "criado_em": item["criado_em"].isoformat(),
        "atualizado_em": item["atualizado_em"].isoformat(),
        "revisado_em": item["revisado_em"].isoformat() if item["revisado_em"] else None,
    }


def _analise_juridica_json(item: dict, reutilizada: bool = False) -> dict:
    return {
        "estado": "CONCLUIDA",
        "id": str(item["id"]),
        "numero_matricula": item["matricula_numero"],
        "resultado_hash": item["resultado_hash"],
        "base_hash": item["base_hash"],
        "modelo": item["modelo"],
        "parecer": item["parecer"],
        "fontes": item["fontes"],
        "criado_em": item["criado_em"].isoformat(),
        "reutilizada": reutilizada,
        "aviso": "Análise automática fundamentada na base jurídica vigente do AERI.",
    }


def _executar_agente_na_matricula(
    numero: int,
    texto: str,
    resultado: dict,
    request: Request,
    usuario: str,
) -> dict:
    """Executa o agente como etapa automática da análise, sem bloquear o motor em caso de indisponibilidade."""
    # O SDK oficial valida assinatura, emissor, projeto e ambiente antes que a
    # credencial efêmera seja aceita. Nunca se confia diretamente no cabeçalho.
    token_oidc = ""
    cabecalho_oidc = request.headers.get("x-vercel-oidc-token")
    if isinstance(cabecalho_oidc, str) and cabecalho_oidc:
        try:
            definir_cabecalhos_oidc(request.headers)
            candidato = get_vercel_oidc_token()
            verify_vercel_oidc_token(candidato)
            token_oidc = candidato
        except (VercelOidcTokenError, VercelOidcVerificationError):
            logger.warning("conferencia_matricula_oidc_invalido numero=%s", numero)
        finally:
            definir_cabecalhos_oidc(None)
    if not agente_juridico_configurado(token_oidc):
        logger.warning("conferencia_matricula_nao_configurada numero=%s", numero)
        return {
            "estado": "AGUARDANDO_CONFIGURACAO",
            "mensagem": "O agente jurídico ainda não foi ativado no servidor.",
        }
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                base_hash = hash_base_juridica_cursor(cursor)
                cursor.execute(
                    """SELECT * FROM analises_juridicas_aeri
                    WHERE matricula_numero=%s AND resultado_hash=%s AND base_hash=%s""",
                    (numero, resultado["resultado_hash"], base_hash),
                )
                existente = cursor.fetchone()
                if existente:
                    return _analise_juridica_json(existente, reutilizada=True)
                cursor.execute(
                    """SELECT COUNT(*) AS total FROM analises_juridicas_aeri
                    WHERE criado_em >= CURRENT_DATE"""
                )
                if cursor.fetchone()["total"] >= limite_agente_juridico_diario():
                    logger.warning("conferencia_matricula_limite_atingido numero=%s", numero)
                    return {
                        "estado": "LIMITE_ATINGIDO",
                        "mensagem": "O limite diário do agente jurídico foi atingido.",
                    }
                trechos = buscar_trechos_cursor(cursor, resultado, texto)
        if not trechos:
            logger.warning("conferencia_matricula_base_insuficiente numero=%s", numero)
            return {
                "estado": "BASE_INSUFICIENTE",
                "mensagem": "A base jurídica não encontrou fontes suficientes para esta matrícula.",
            }
        analise = executar_agente_juridico(texto, resultado, trechos, token_oidc=token_oidc)
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                item = salvar_analise_juridica_cursor(
                    cursor, numero, resultado["resultado_hash"], base_hash, analise, usuario,
                )
                registrar_auditoria_cursor(
                    cursor, request, "analisar_matricula_agente_juridico", "sucesso", usuario,
                    str(numero), {
                        "resultado_hash": resultado["resultado_hash"],
                        "base_hash": base_hash,
                        "conclusao": item["conclusao"],
                        "fontes": len(item["fontes"]),
                    },
                )
            conexao.commit()
        return _analise_juridica_json(item)
    except RuntimeError as erro:
        logger.warning(
            "conferencia_matricula_indisponivel numero=%s motivo=%s",
            numero,
            str(erro)[:180],
        )
        registrar_auditoria(
            request, "analisar_matricula_agente_juridico", "indisponivel", usuario, str(numero),
        )
        return {"estado": "INDISPONIVEL", "mensagem": str(erro)}


def _controle_qualidade_publico(analise: dict) -> dict:
    """Expõe somente o estado operacional, sem revelar provedor, parecer ou fontes."""
    if analise.get("estado") != "CONCLUIDA":
        return {"estado": "NAO_CONFERIDO", "dominios": []}
    dominios_revisao = []
    for item in (analise.get("parecer") or {}).get("analises") or []:
        if item.get("comparacao") != "CONFERE" or item.get("status") != "CONCLUIDO":
            dominio = str(item.get("dominio") or "").upper()
            if dominio in {"ONUS", "IMOVEL", "PROPRIETARIOS"}:
                dominios_revisao.append(dominio)
    return {
        "estado": "REVISAR" if dominios_revisao else "CONFERIDO",
        "dominios": list(dict.fromkeys(dominios_revisao)),
    }


@router.post("/analisar", dependencies=[Depends(proteger_csrf)])
def analisar(dados: dict, request: Request, usuario: str = Depends(exigir_perfis("ADMIN"))):
    texto = str(dados.get("texto", ""))
    if not texto.strip() or len(texto) > 5_000_000:
        raise HTTPException(status_code=413, detail="A matrícula excede o limite permitido.")
    numero_informado = str(dados.get("numero_matricula") or "").strip()
    numero = None
    if numero_informado:
        try:
            numero = normalizar_numero_matricula(numero_informado)
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from erro
    resultado = analisar_matricula(
        texto,
        regras_aprendidas=_regras_aprovadas(),
        numero_matricula=numero,
    )
    resultado["numero_matricula"] = numero or resultado.get("numero_matricula") or "MANUAL"
    resultado["origem"] = "ENTRADA MANUAL"
    analise_secundaria = _executar_agente_na_matricula(
        int(numero or 0), texto, resultado, request, usuario,
    )
    resultado["controle_qualidade"] = _controle_qualidade_publico(analise_secundaria)
    registrar_auditoria(request, "analisar_matricula_texto_manual", "sucesso", usuario, numero)
    return resultado


@router.post("/analisar/matricula", dependencies=[Depends(proteger_csrf)])
def analisar_por_numero(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("processar_matricula")),
):
    try:
        numero = normalizar_numero_matricula(dados.get("numero_matricula"))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    try:
        matricula = cliente_tri7().buscar_texto_matricula(numero)
    except (MatriculaTri7NaoEncontrada, MatriculaTri7SemTexto) as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except ConfiguracaoTri7Invalida as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    except ErroTri7 as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro
    resultado = analisar_matricula(
        matricula["texto"],
        regras_aprendidas=_regras_aprovadas(),
        numero_matricula=matricula["numero_matricula"],
    )
    resultado["numero_matricula"] = matricula["numero_matricula"]
    resultado["origem"] = "TRI7"
    analise_secundaria = _executar_agente_na_matricula(
        int(numero), matricula["texto"], resultado, request, usuario,
    )
    resultado["controle_qualidade"] = _controle_qualidade_publico(analise_secundaria)
    registrar_auditoria(request, "consultar_e_analisar_matricula_tri7", "sucesso", usuario, numero)
    return resultado


@router.post("/analisar/base-juridica/importar", dependencies=[Depends(proteger_csrf)])
async def importar_base_juridica(
    request: Request,
    usuario: str = Depends(exigir_permissao("revisar_auditoria")),
):
    tamanho = int(request.headers.get("content-length", "0") or 0)
    if tamanho > 4_000_000:
        raise HTTPException(status_code=413, detail="O lote jurídico excede o limite permitido.")
    conteudo = await request.body()
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                resumo = importar_lote_juridico_cursor(cursor, conteudo, usuario)
            conexao.commit()
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    registrar_auditoria(
        request,
        "importar_base_juridica",
        "sucesso",
        usuario,
        detalhes={
            "recebidos": resumo["recebidos"],
            "indexados": resumo["indexados"],
            "trechosIndexados": resumo["trechos_indexados"],
        },
    )
    return resumo


@router.post("/analisar/feedback", dependencies=[Depends(proteger_csrf)])
def registrar_feedback_analise(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("processar_matricula")),
):
    feedback = _validar_feedback(dados)
    status = "RESOLVIDA" if feedback["avaliacao"] == "CORRETO" else "PENDENTE"
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO divergencias_analise_aeri
                (id, numero_matricula, motor_versao, resultado_hash, avaliacao,
                 dominios, comentario, resumo, status, criado_por)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
                RETURNING *""",
                (
                    uuid4(), feedback["numero"], feedback["motor_versao"],
                    feedback["resultado_hash"], feedback["avaliacao"],
                    json.dumps(feedback["dominios"]), feedback["comentario"],
                    json.dumps(feedback["resumo"], ensure_ascii=False), status, usuario,
                ),
            )
            item = cursor.fetchone()
            registrar_auditoria_cursor(
                cursor, request, "avaliar_analise", "sucesso", usuario,
                feedback["numero"], {"avaliacao": feedback["avaliacao"], "dominios": feedback["dominios"]},
            )
        conexao.commit()
    return _divergencia_json(item)


@router.get("/analisar/divergencias")
def listar_divergencias(
    status: str = "PENDENTE",
    _admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    status = status.strip().upper()
    if status not in {"PENDENTE", "RESOLVIDA", "ARQUIVADA"}:
        raise HTTPException(status_code=422, detail="Status inválido.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM divergencias_analise_aeri
                WHERE status=%s AND avaliacao='REVISAR'
                ORDER BY criado_em DESC LIMIT 300""",
                (status,),
            )
            return [_divergencia_json(item) for item in cursor.fetchall()]


@router.post("/analisar/divergencias/{divergencia_id}/resolver", dependencies=[Depends(proteger_csrf)])
def resolver_divergencia(
    divergencia_id: str,
    dados: dict,
    request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    try:
        identificador = UUID(divergencia_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Identificador inválido.") from exc
    status = str(dados.get("status", "RESOLVIDA")).strip().upper()
    if status not in {"RESOLVIDA", "ARQUIVADA"}:
        raise HTTPException(status_code=422, detail="Status inválido.")
    resolucao = str(dados.get("resolucao", "")).strip()
    if len(resolucao) > 1000:
        raise HTTPException(status_code=422, detail="Resolução excede 1.000 caracteres.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE divergencias_analise_aeri SET status=%s, resolucao=%s,
                revisado_por=%s, revisado_em=NOW(), atualizado_em=NOW()
                WHERE id=%s AND status='PENDENTE' RETURNING *""",
                (status, resolucao, admin, identificador),
            )
            item = cursor.fetchone()
            if item:
                registrar_auditoria_cursor(
                    cursor, request, "resolver_divergencia_analise", "sucesso", admin,
                    str(identificador), {"status": status},
                )
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Divergência pendente não encontrada.")
    return _divergencia_json(item)


@router.post("/analisar/aprendizado/sugestoes", dependencies=[Depends(proteger_csrf)])
def sugerir_regra_aprendizado(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    try:
        sugestao = validar_sugestao_aprendizado(dados)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO regras_aprendizado_aeri
                (id, expressao, expressao_normalizada, categoria, impacta_resultado,
                 tipo_onus, justificativa, criado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (expressao_normalizada, categoria, tipo_onus)
                DO UPDATE SET votos=regras_aprendizado_aeri.votos + 1,
                    status=CASE
                        WHEN regras_aprendizado_aeri.status = 'REJEITADA' THEN 'PENDENTE'
                        ELSE regras_aprendizado_aeri.status
                    END,
                    aprovado_por=CASE
                        WHEN regras_aprendizado_aeri.status = 'REJEITADA' THEN NULL
                        ELSE regras_aprendizado_aeri.aprovado_por
                    END,
                    aprovado_em=CASE
                        WHEN regras_aprendizado_aeri.status = 'REJEITADA' THEN NULL
                        ELSE regras_aprendizado_aeri.aprovado_em
                    END,
                    justificativa=CASE
                        WHEN EXCLUDED.justificativa <> '' THEN EXCLUDED.justificativa
                        ELSE regras_aprendizado_aeri.justificativa
                    END,
                    atualizado_em=NOW()
                RETURNING *""",
                (
                    uuid4(),
                    sugestao["expressao"],
                    sugestao["expressao_normalizada"],
                    sugestao["categoria"],
                    sugestao["impacta_resultado"],
                    sugestao["tipo_onus"],
                    sugestao["justificativa"],
                    usuario,
                ),
            )
            item = cursor.fetchone()
            registrar_auditoria_cursor(
                cursor,
                request,
                "sugerir_regra_aprendizado",
                "sucesso",
                usuario,
                str(item["id"]),
                {"categoria": item["categoria"], "status": item["status"]},
            )
        conexao.commit()
    return _regra_json(item)


@router.get("/analisar/aprendizado/sugestoes")
def listar_regras_aprendizado(
    status: str = "PENDENTE",
    _admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    status = status.strip().upper()
    if status not in {"PENDENTE", "APROVADA", "REJEITADA"}:
        raise HTTPException(status_code=422, detail="Status inválido.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM regras_aprendizado_aeri
                WHERE status=%s
                ORDER BY votos DESC, atualizado_em DESC
                LIMIT 200""",
                (status,),
            )
            return [_regra_json(item) for item in cursor.fetchall()]


@router.post("/analisar/aprendizado/sugestoes/{regra_id}/aprovar", dependencies=[Depends(proteger_csrf)])
def aprovar_regra_aprendizado(
    regra_id: str,
    request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    try:
        identificador = validar_id_regra(regra_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT criado_por FROM regras_aprendizado_aeri WHERE id=%s",
                (identificador,),
            )
            regra = cursor.fetchone()
            if not regra:
                raise HTTPException(status_code=404, detail="Regra de aprendizado não encontrada.")
            if regra["criado_por"] == admin:
                # Exige um segundo revisor: quem sugere a regra não pode ser
                # quem aprova, já que isso muda a classificação de ônus para
                # todo mundo sem nenhuma revisão independente.
                raise HTTPException(
                    status_code=403,
                    detail="Quem sugeriu a regra não pode aprová-la — peça a outro ADM/SUBSTITUTO.",
                )
            cursor.execute(
                """UPDATE regras_aprendizado_aeri
                SET status='APROVADA', aprovado_por=%s, aprovado_em=NOW(), atualizado_em=NOW()
                WHERE id=%s RETURNING *""",
                (admin, identificador),
            )
            item = cursor.fetchone()
            registrar_auditoria_cursor(cursor, request, "aprovar_regra_aprendizado", "sucesso", admin, str(identificador))
        conexao.commit()
    return _regra_json(item)


@router.post("/analisar/aprendizado/sugestoes/{regra_id}/rejeitar", dependencies=[Depends(proteger_csrf)])
def rejeitar_regra_aprendizado(
    regra_id: str,
    request: Request,
    admin: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    try:
        identificador = validar_id_regra(regra_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE regras_aprendizado_aeri
                SET status='REJEITADA', aprovado_por=%s, atualizado_em=NOW()
                WHERE id=%s RETURNING *""",
                (admin, identificador),
            )
            item = cursor.fetchone()
            if item:
                registrar_auditoria_cursor(cursor, request, "rejeitar_regra_aprendizado", "sucesso", admin, str(identificador))
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Regra de aprendizado não encontrada.")
    return _regra_json(item)
