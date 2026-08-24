import hmac
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, executar_manutencao_banco, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.analise.onus import processar_atos
from backend.app.proprietarios import calcular_cadeia_dominial
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.auditoria_integrada import (
    construir_resumo_auditoria,
    executar_revisao_complementar,
    limite_complementar_diario,
    mascarar_documentos_estrutura,
    mascarar_documentos_texto,
)
from backend.app.servicos.buscas import (
    HASH_DOCUMENTOS_VERSAO,
    construir_indice_matricula,
    hash_documento,
    normalizar_documento,
    normalizar_nome,
    validar_configuracao_buscas,
)
from backend.app.servicos.tri7 import (
    AutenticacaoTri7Falhou,
    ConfiguracaoTri7Invalida,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    cliente_tri7,
)

from backend.app.rotas.buscas_indexacao import (
    _consultar_lote,
    _consultar_matricula,
    _estado_json,
    _executar_sincronizacao,
    _limpar_erro,
    _proximo_modo_automatico,
    _registrar_erro,
    _salvar_auditoria,
    _salvar_ausencia,
    _salvar_indice,
    _tentar_revisao_complementar,
)


router = APIRouter(
    prefix="/api/buscas",
    tags=["busca de titularidade"],
    dependencies=[Depends(preparar_banco)],
)
LEASE_SEGUNDOS = 300
MAX_WORKERS_TRI7 = 3
MAX_WORKERS_REPROCESSAMENTO = 6






















@router.get("")
def pesquisar_titularidade(
    termo: str = Query(..., min_length=3, max_length=300),
    limite: int = Query(50, ge=1, le=100),
    _usuario: str = Depends(exigir_permissao("acessar_buscas")),
    pagina: int = Query(1, ge=1),
):
    documento = normalizar_documento(termo) if not any(caractere.isalpha() for caractere in termo) else ""
    parametros = []
    if documento:
        if len(documento) not in {11, 14}:
            raise HTTPException(status_code=422, detail="Informe o CPF ou CNPJ completo.")
        try:
            documento_protegido = hash_documento(documento)
        except RuntimeError as erro:
            raise HTTPException(status_code=503, detail=str(erro)) from erro
        filtro = "p.documento_hash=%s"
        parametros.append(documento_protegido)
        tipo_busca = "DOCUMENTO_EXATO"
    else:
        nome = normalizar_nome(termo)
        if len(nome) < 3:
            raise HTTPException(status_code=422, detail="Informe ao menos três caracteres do nome.")
        filtro = "(p.nome_busca=%s OR p.nome_busca LIKE %s)"
        parametros.extend((nome, f"%{nome}%"))
        tipo_busca = "NOME"

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if documento:
                cursor.execute(
                    """SELECT COUNT(*) AS total FROM matriculas_busca_aeri
                    WHERE texto_hash IS NOT NULL
                      AND documentos_hash_versao IS DISTINCT FROM %s""",
                    (HASH_DOCUMENTOS_VERSAO,),
                )
                if cursor.fetchone()["total"]:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "A busca por CPF/CNPJ está temporariamente indisponível enquanto "
                            "os documentos são reindexados com a nova chave de segurança. "
                            "A pesquisa por nome continua disponível."
                        ),
                    )
            cursor.execute(
                f"""SELECT COUNT(*) AS total
                FROM proprietarios_matriculas_busca_aeri p
                JOIN matriculas_busca_aeri m ON m.numero=p.matricula_numero
                WHERE {filtro}""",
                tuple(parametros),
            )
            total = int(cursor.fetchone()["total"] or 0)
            deslocamento = (pagina - 1) * limite
            cursor.execute(
                f"""SELECT m.numero, m.situacao, m.confianca AS confianca_matricula,
                m.consultado_em, p.nome, p.documento_mascarado, p.tipo_documento,
                p.proporcao, p.origem, p.confianca,
                CASE WHEN %s='NOME' AND p.nome_busca=%s THEN 'NOME_EXATO'
                     WHEN %s='DOCUMENTO_EXATO' THEN 'DOCUMENTO_EXATO'
                     ELSE 'NOME_PARCIAL' END AS correspondencia
                FROM proprietarios_matriculas_busca_aeri p
                JOIN matriculas_busca_aeri m ON m.numero=p.matricula_numero
                WHERE {filtro}
                ORDER BY
                    CASE WHEN p.nome_busca=%s THEN 0 ELSE 1 END,
                    p.nome, m.numero DESC LIMIT %s OFFSET %s""",
                (
                    tipo_busca, normalizar_nome(termo), tipo_busca,
                    *parametros, normalizar_nome(termo), limite, deslocamento,
                ),
            )
            itens = cursor.fetchall()
    return {
        "termo": termo.strip(),
        "tipoBusca": tipo_busca,
        "quantidade": len(itens),
        "total": total,
        "pagina": pagina,
        "porPagina": limite,
        "totalPaginas": math.ceil(total / limite) if total else 0,
        "itens": [
            {
                "matricula": item["numero"], "nome": item["nome"],
                "documento": item["documento_mascarado"], "tipoDocumento": item["tipo_documento"],
                "proporcao": item["proporcao"], "origem": item["origem"],
                "situacao": item["situacao"], "confianca": item["confianca"],
                "correspondencia": item["correspondencia"],
                "consultadoEm": item["consultado_em"].isoformat(),
            }
            for item in itens
        ],
    }


@router.get("/exportacao")
def exportar_pesquisa_titularidade(
    termo: str = Query(..., min_length=3, max_length=300),
    _usuario: str = Depends(exigir_permissao("acessar_buscas")),
):
    """Devolve o conjunto completo usado no texto da pesquisa.

    A tabela aceita nome parcial para ajudar a localizar a pessoa. Já o texto
    tem efeito declaratório e, por segurança, só pode usar nome normalizado
    exato ou CPF/CNPJ completo. A consulta única também evita dezenas de
    requisições paginadas pelo navegador.
    """
    documento = normalizar_documento(termo) if not any(c.isalpha() for c in termo) else ""
    if documento:
        if len(documento) not in {11, 14}:
            raise HTTPException(status_code=422, detail="Informe o CPF ou CNPJ completo.")
        try:
            valor = hash_documento(documento)
        except RuntimeError as erro:
            raise HTTPException(status_code=503, detail=str(erro)) from erro
        filtro = "p.documento_hash=%s"
        tipo_busca = "DOCUMENTO_EXATO"
    else:
        valor = normalizar_nome(termo)
        if len(valor) < 3:
            raise HTTPException(status_code=422, detail="Informe ao menos três caracteres do nome.")
        filtro = "p.nome_busca=%s"
        tipo_busca = "NOME_EXATO"

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if documento:
                cursor.execute(
                    """SELECT COUNT(*) AS total FROM matriculas_busca_aeri
                    WHERE texto_hash IS NOT NULL
                      AND documentos_hash_versao IS DISTINCT FROM %s""",
                    (HASH_DOCUMENTOS_VERSAO,),
                )
                if cursor.fetchone()["total"]:
                    raise HTTPException(
                        status_code=503,
                        detail="A busca por CPF/CNPJ aguarda a reindexação segura dos documentos.",
                    )
            cursor.execute(
                f"""SELECT COUNT(*) AS total
                FROM proprietarios_matriculas_busca_aeri p
                JOIN matriculas_busca_aeri m ON m.numero=p.matricula_numero
                WHERE {filtro}""",
                (valor,),
            )
            total = int(cursor.fetchone()["total"] or 0)
            if total > 5_000:
                raise HTTPException(
                    status_code=422,
                    detail="A pesquisa exata retornou mais de 5.000 linhas; refine pelo CPF/CNPJ.",
                )
            cursor.execute(
                f"""SELECT m.numero, m.situacao, m.consultado_em,
                p.nome, p.documento_mascarado, p.tipo_documento,
                p.proporcao, p.origem, p.confianca
                FROM proprietarios_matriculas_busca_aeri p
                JOIN matriculas_busca_aeri m ON m.numero=p.matricula_numero
                WHERE {filtro}
                ORDER BY m.numero, p.ordem""",
                (valor,),
            )
            itens = cursor.fetchall()
    return {
        "termo": termo.strip(),
        "tipoBusca": tipo_busca,
        "total": total,
        "exata": True,
        "itens": [
            {
                "matricula": item["numero"], "nome": item["nome"],
                "documento": item["documento_mascarado"],
                "tipoDocumento": item["tipo_documento"],
                "proporcao": item["proporcao"], "origem": item["origem"],
                "situacao": item["situacao"], "confianca": item["confianca"],
                "correspondencia": tipo_busca,
                "consultadoEm": item["consultado_em"].isoformat(),
            }
            for item in itens
        ],
    }


@router.get("/status")
def status_buscas(_usuario: str = Depends(exigir_permissao("acessar_buscas"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            return _estado_json(cursor)


@router.get("/erros")
def listar_erros(_usuario: str = Depends(exigir_permissao("revisar_auditoria"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT numero, modo, erro, tentativas, ultima_tentativa_em
                FROM matriculas_busca_erros_aeri
                ORDER BY tentativas DESC, ultima_tentativa_em DESC LIMIT 200"""
            )
            return [{
                "numero": item["numero"], "modo": item["modo"], "erro": item["erro"],
                "tentativas": item["tentativas"],
                "ultimaTentativaEm": item["ultima_tentativa_em"].isoformat(),
            } for item in cursor.fetchall()]


@router.get("/auditoria/pendencias")
def listar_pendencias_auditoria(
    limite: int = Query(100, ge=1, le=300),
    inicio: int = Query(0, ge=0),
    _usuario: str = Depends(exigir_permissao("revisar_auditoria")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT matricula_numero, estado, prioridade, confianca_onus,
                confianca_cadeia, confianca_imovel, alertas, complemento_status,
                complemento_diagnostico, analisado_em
                FROM auditorias_matriculas_aeri
                WHERE estado='REVISAR'
                ORDER BY CASE prioridade WHEN 'P0-CRITICA' THEN 0 ELSE 1 END,
                         matricula_numero LIMIT %s OFFSET %s""",
                (limite, inicio),
            )
            return [{
                "matricula": item["matricula_numero"],
                "estado": item["estado"],
                "prioridade": item["prioridade"],
                "confiancaOnus": item["confianca_onus"],
                "confiancaCadeia": item["confianca_cadeia"],
                "confiancaImovel": item["confianca_imovel"],
                "alertas": item["alertas"] or [],
                "analiseComplementar": item["complemento_status"],
                "diagnosticoComplementar": item["complemento_diagnostico"],
                "analisadoEm": item["analisado_em"].isoformat(),
            } for item in cursor.fetchall()]


@router.post("/auditoria/{numero}/diagnostico", dependencies=[Depends(proteger_csrf)])
def diagnosticar_pendencia_auditoria(
    numero: int,
    request: Request,
    usuario: str = Depends(exigir_permissao("revisar_auditoria")),
    detalhar: bool = Query(False),
):
    """Reconsulta uma matrícula sem persistir o texto e devolve atos mascarados.

    A rota existe para que o Auditor consiga distinguir falha do analisador de
    falso positivo da auditoria. CPF e CNPJ são removidos antes da resposta e
    nenhum trecho é gravado no banco ou no log operacional.
    """
    if numero <= 0:
        raise HTTPException(status_code=422, detail="Número de matrícula inválido.")
    resultados, falha = _consultar_lote([numero])
    if falha:
        raise HTTPException(status_code=502, detail=falha)
    if not resultados or resultados[0]["status"] != "OK":
        status = resultados[0]["status"] if resultados else "ERRO"
        codigo = 404 if status in {"NAO_ENCONTRADA", "SEM_TEXTO"} else 502
        raise HTTPException(status_code=codigo, detail="Matrícula indisponível para diagnóstico.")

    texto = resultados[0]["texto"]
    resultado = analisar_matricula(texto, numero_matricula=str(numero))
    from scripts.auditar_semantica_tri7 import auditar_texto

    auditoria = auditar_texto(numero, texto, resultado=resultado)
    atos = processar_atos(texto)
    primeiro_ato = min(
        (texto.find(ato.descricao) for ato in atos if texto.find(ato.descricao) >= 0),
        default=len(texto),
    )
    resposta = {
        "numero": numero,
        "resultado": resultado.get("resultado"),
        "publicidade": resultado.get("publicidade"),
        "cabecalho": mascarar_documentos_texto(texto[:primeiro_ato])[:12_000],
        "proprietarios": [
            {
                "nome": item.get("nome", ""),
                "documento": "[DOCUMENTO]" if item.get("cpf") else "",
                "proporcao": item.get("proporcao", ""),
                "proporcaoIncerta": bool(item.get("proporcao_incerta")),
            }
            for item in resultado.get("proprietarios_atuais", [])
        ],
        "imovel": mascarar_documentos_estrutura(resultado.get("imovel", {})),
        "atos": [
            {
                "codigo": ato.codigo,
                "categoria": ato.categoria,
                "status": ato.status,
                "tipoOnus": ato.tipo_onus,
                "canceladoPor": ato.cancelado_por,
                "cancelaAtos": list(ato.cancela_atos or []),
                "descricao": mascarar_documentos_texto(ato.descricao)[:12_000],
            }
            for ato in atos
        ],
        "auditoria": mascarar_documentos_estrutura({
            chave: valor
            for chave, valor in auditoria.items()
            if chave not in {"texto", "proprietarios_detalhes"}
        }),
        "meta": {"textoPersistido": False, "documentosMascarados": True},
    }
    if detalhar is True:
        resposta["cadeiaPassos"] = [
            {
                "codigo": ato.codigo,
                "proprietarios": [
                    {
                        "nome": item.get("nome", ""),
                        "proporcao": item.get("proporcao", ""),
                        "proporcaoIncerta": bool(item.get("proporcao_incerta")),
                    }
                    for item in calcular_cadeia_dominial(atos[:indice], texto)
                ],
            }
            for indice, ato in enumerate(atos, start=1)
        ]
    registrar_auditoria(
        request, "diagnosticar_pendencia_matricula", "sucesso", usuario, str(numero)
    )
    return resposta


@router.post("/auditoria/reprocessar", dependencies=[Depends(proteger_csrf)])
def reprocessar_pendencias_auditoria(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("revisar_auditoria")),
):
    """Reexecuta um lote da fila atual sem perder a posição de retomada."""
    try:
        apos = max(0, int(dados.get("apos", 0) or 0))
        tamanho = max(1, min(int(dados.get("tamanho", 20) or 20), 60))
    except (TypeError, ValueError) as erro:
        raise HTTPException(status_code=422, detail="Parâmetros de reprocessamento inválidos.") from erro
    alertas = [
        item.strip().upper()
        for item in (dados.get("alertas") or [])
        if isinstance(item, str)
        and re.fullmatch(r"[A-Z0-9_\-]{3,100}", item.strip().upper())
    ]
    try:
        validar_configuracao_buscas()
    except RuntimeError as erro:
        raise HTTPException(
            status_code=503,
            detail="Reprocessamento indisponível: configuração de segurança ausente no servidor.",
        ) from erro

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE sincronizacao_matriculas_busca_aeri SET travado_em=NOW()
                WHERE id=1 AND (travado_em IS NULL OR travado_em < NOW() - make_interval(secs => %s))
                RETURNING id""",
                (LEASE_SEGUNDOS,),
            )
            if cursor.fetchone() is None:
                conexao.commit()
                raise HTTPException(status_code=409, detail="Já existe uma indexação em andamento.")
            conexao.commit()
            try:
                if alertas:
                    cursor.execute(
                        """SELECT matricula_numero FROM auditorias_matriculas_aeri
                        WHERE estado='REVISAR' AND matricula_numero > %s
                          AND alertas ?| %s::text[]
                        ORDER BY matricula_numero LIMIT %s""",
                        (apos, alertas, tamanho),
                    )
                else:
                    cursor.execute(
                        """SELECT matricula_numero FROM auditorias_matriculas_aeri
                        WHERE estado='REVISAR' AND matricula_numero > %s
                        ORDER BY matricula_numero LIMIT %s""",
                        (apos, tamanho),
                    )
                numeros = [item["matricula_numero"] for item in cursor.fetchall()]
                if not numeros:
                    estado = _estado_json(cursor)
                    conexao.commit()
                    return {
                        "processados": 0,
                        "validadas": 0,
                        "aindaPendentes": 0,
                        "falhas": 0,
                        "proximo": apos,
                        "concluido": True,
                        "estado": estado,
                    }

                resultados, falha_fatal = _consultar_lote(
                    numeros, max_workers=MAX_WORKERS_REPROCESSAMENTO
                )
                processados = validadas = ainda_pendentes = falhas = 0
                ultimo_processado = apos
                erros = []
                for resultado in resultados:
                    numero = resultado["numero"]
                    if resultado["status"] == "OK":
                        _indice, _novo, _alterado, auditoria, _complemento = _salvar_indice(
                            cursor, numero, resultado["texto"], permitir_complemento=False,
                        )
                        validadas += int(auditoria["estado"] == "VALIDADA_AUTOMATICAMENTE")
                        ainda_pendentes += int(auditoria["estado"] == "REVISAR")
                    elif resultado["status"] in {"NAO_ENCONTRADA", "SEM_TEXTO"}:
                        _salvar_ausencia(cursor, numero, resultado["status"])
                        validadas += 1
                    else:
                        _registrar_erro(cursor, numero, "AUDITORIA", resultado["erro"])
                        falhas += 1
                        erros.append({"numero": numero, "erro": str(resultado["erro"])[:180]})
                    processados += 1
                    ultimo_processado = numero

                registrar_auditoria_cursor(
                    cursor,
                    request,
                    "reprocessar_pendencias_auditoria",
                    "sucesso" if not falha_fatal else "parcial",
                    usuario,
                    detalhes={
                        "processados": processados,
                        "validadas": validadas,
                        "aindaPendentes": ainda_pendentes,
                        "falhas": falhas,
                        "de": numeros[0],
                        "ate": ultimo_processado,
                    },
                )
                estado = _estado_json(cursor)
                conexao.commit()
                return {
                    "processados": processados,
                    "validadas": validadas,
                    "aindaPendentes": ainda_pendentes,
                    "falhas": falhas,
                    "erros": erros,
                    "falha": falha_fatal,
                    "proximo": ultimo_processado,
                    "concluido": False,
                    "estado": estado,
                }
            finally:
                conexao.rollback()
                cursor.execute("UPDATE sincronizacao_matriculas_busca_aeri SET travado_em=NULL WHERE id=1")
                conexao.commit()




@router.post("/sincronizar", dependencies=[Depends(proteger_csrf)])
def sincronizar_buscas(
    dados: dict, request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    modo = str(dados.get("modo", "INICIAL")).strip().upper()
    if modo not in {"INICIAL", "NOVOS", "REVISAO", "ERROS"}:
        raise HTTPException(status_code=422, detail="Modo de indexação inválido.")
    try:
        tamanho = max(1, min(int(dados.get("tamanho", 20)), 30))
        limite = int(dados.get("limite", 0) or 0)
    except (TypeError, ValueError) as erro:
        raise HTTPException(status_code=422, detail="Parâmetros de indexação inválidos.") from erro
    return _executar_sincronizacao(modo, tamanho, limite, request, usuario)


@router.post("/{numero}/revisar", dependencies=[Depends(proteger_csrf)])
def revisar_matricula_busca(
    numero: int, request: Request,
    usuario: str = Depends(exigir_permissao("revisar_auditoria")),
):
    if numero <= 0:
        raise HTTPException(status_code=422, detail="Número de matrícula inválido.")
    try:
        validar_configuracao_buscas()
    except RuntimeError as erro:
        raise HTTPException(
            status_code=503,
            detail="Revisão indisponível: configuração de segurança ausente no servidor.",
        ) from erro
    resultados, falha = _consultar_lote([numero])
    if falha:
        raise HTTPException(status_code=502, detail=falha)
    if not resultados:
        raise HTTPException(status_code=502, detail="A Tri7 não concluiu a consulta.")
    resultado = resultados[0]
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if resultado["status"] == "OK":
                indice, novo, alterado, auditoria, _complemento = _salvar_indice(
                    cursor, numero, resultado["texto"], permitir_complemento=True,
                )
                cursor.execute(
                    """UPDATE sincronizacao_matriculas_busca_aeri
                    SET limite_inicial=GREATEST(limite_inicial,%s),
                        ultimo_conhecido=GREATEST(ultimo_conhecido,%s),
                        ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""", (numero, numero),
                )
                registrar_auditoria_cursor(
                    cursor, request, "revisar_matricula_busca", "sucesso", usuario,
                    detalhes={"numero": numero, "novo": novo, "alterado": alterado,
                              "situacao": indice["situacao"],
                              "estadoAuditoria": auditoria["estado"]},
                )
                estado = _estado_json(cursor)
                conexao.commit()
                return {"numero": numero, "novo": novo, "alterado": alterado,
                        "situacao": indice["situacao"],
                        "estadoAuditoria": auditoria["estado"], "estado": estado}
            if resultado["status"] in {"NAO_ENCONTRADA", "SEM_TEXTO"}:
                _salvar_ausencia(cursor, numero, resultado["status"])
                conexao.commit()
                raise HTTPException(status_code=404, detail="Matrícula sem texto disponível na Tri7.")
            _registrar_erro(cursor, numero, "MANUAL", resultado["erro"])
            conexao.commit()
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a Tri7: {resultado['erro']}")




@router.get("/cron")
def cron_buscas(request: Request):
    segredo = os.getenv("CRON_SECRET", "")
    autorizacao = request.headers.get("authorization", "")
    if not segredo or not hmac.compare_digest(autorizacao, f"Bearer {segredo}"):
        raise HTTPException(status_code=401, detail="Não autorizado.")
    executar_manutencao_banco()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            modo = _proximo_modo_automatico(cursor)
    resultado = _executar_sincronizacao(modo, 30, 0, request, "cron")
    if modo == "NOVOS":
        resultado["revisao"] = _executar_sincronizacao("REVISAO", 30, 0, request, "cron")
    return resultado
