from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.rotas.buscas import _salvar_indice as _salvar_indice_matricula
from backend.app.rotas.registros_auxiliares import _salvar_indice as _salvar_indice_auxiliar
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.livro_protocolos import (
    codigos_atos_confirmados,
    conferir_protocolo,
    extrair_protocolos_pdf,
    hash_regras_livro_protocolos,
    inferir_data_esperada,
    janelas_livro_protocolos,
    montar_protocolos_do_dia,
    natureza_permite_excecao,
    normalizar_tema,
    referencias_textos_protocolo,
    registros_alterados_no_protocolo,
)
from backend.app.servicos.tri7 import ErroTri7, ProtocoloTri7NaoEncontrado, cliente_tri7


router = APIRouter(
    prefix="/api/livro-protocolos",
    tags=["livro de protocolos"],
    dependencies=[Depends(preparar_banco)],
)


def _assinaturas_ocorrencias(resultado: dict) -> set[tuple[str, str, str]]:
    return {
        (str(item.get("numero")), str(ocorrencia.get("regra")), str(ocorrencia.get("descricao")))
        for item in resultado.get("protocolos") or []
        for ocorrencia in item.get("ocorrencias") or []
    }


def _salvar_rodada_livro(
    resultado: dict, data_esperada: date, fonte: str, usuario: str,
) -> dict:
    identificador = uuid4()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, resultado FROM livro_protocolos_rodadas_aeri
                WHERE data_esperada=%s ORDER BY criado_em ASC LIMIT 1""",
                (data_esperada,),
            )
            primeira = cursor.fetchone()
            cursor.execute(
                """INSERT INTO livro_protocolos_rodadas_aeri
                (id, data_esperada, fonte, regras_hash, resultado, resumo, criado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    identificador, data_esperada, fonte, hash_regras_livro_protocolos(),
                    Jsonb(resultado), Jsonb(resultado.get("resumo") or {}), usuario,
                ),
            )
        conexao.commit()
    comparacao = None
    if primeira:
        anteriores = _assinaturas_ocorrencias(primeira["resultado"])
        atuais = _assinaturas_ocorrencias(resultado)
        protocolos_alterados = sorted({
            numero for numero, _regra, _descricao in anteriores.symmetric_difference(atuais)
        }, key=lambda numero: (0, int(numero)) if numero.isdigit() else (1, numero))
        comparacao = {
            "primeiraRodadaId": str(primeira["id"]),
            "novasOcorrencias": len(atuais - anteriores),
            "ocorrenciasResolvidas": len(anteriores - atuais),
            "protocolosAlterados": protocolos_alterados[:200],
        }
    return {"rodadaId": str(identificador), "comparacaoPrimeira": comparacao}


def _resumir_resultados_livro(resultados: list[dict]) -> dict:
    return {
        "total": len(resultados),
        "prenotados": sum(1 for r in resultados if r["status"] == "PRENOTADO"),
        "registrados": sum(1 for r in resultados if r["status"] == "REGISTRADO"),
        "semEfeito": sum(1 for r in resultados if r["status"] == "SEM_EFEITO"),
        "indefinidos": sum(1 for r in resultados if r["status"] == "INDEFINIDO"),
        "conferidos": sum(1 for r in resultados if r["conferido"]),
        "falhasConsulta": sum(1 for r in resultados if r["erro"]),
        "comOcorrencias": sum(1 for r in resultados if r["ocorrencias"]),
        "totalOcorrencias": sum(len(r["ocorrencias"]) for r in resultados),
    }


def _analisar_itens_livro(
    itens: list[dict],
    data_esperada: date,
    request: Request,
    usuario: str,
    *,
    cliente=None,
    acao_auditoria: str = "analisar_livro_protocolos",
    fonte: str = "PDF",
    cobertura: dict | None = None,
    salvar_rodada: bool = True,
) -> dict:
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT titulo_tema, natureza_tema
                FROM livro_protocolos_excecoes_natureza_aeri
                WHERE ativa=TRUE AND vigencia_inicio<=%s
                AND (vigencia_fim IS NULL OR vigencia_fim>=%s)""",
                (data_esperada, data_esperada),
            )
            excecoes = frozenset((linha["titulo_tema"], linha["natureza_tema"]) for linha in cursor.fetchall())

    cliente = cliente or cliente_tri7()
    cache_textos: dict[tuple[str, int], tuple[str | None, str | None]] = {}
    cache_atos: dict[tuple[str, int], set[tuple[str, int]]] = {}
    alterados: set[tuple[str, int]] = set()
    resultados = []
    for item in itens:
        registro = {**item, "conferido": False, "ocorrencias": [], "erro": None}
        if item["status"] == "REGISTRADO":
            try:
                protocolo_json = cliente.buscar_protocolo_completo(item["numero"])
                alterados |= registros_alterados_no_protocolo(protocolo_json)
                textos_registros = {}
                falhas_textos = {}
                atos_confirmados = {}
                for referencia in referencias_textos_protocolo(protocolo_json):
                    if referencia not in cache_textos:
                        try:
                            if referencia[0] == "M":
                                resposta_texto = cliente.buscar_texto_matricula(referencia[1])
                            else:
                                resposta_texto = cliente.buscar_texto_registro_auxiliar(referencia[1])
                            cache_textos[referencia] = (resposta_texto["texto"], None)
                        except ErroTri7 as erro:
                            cache_textos[referencia] = (None, str(erro))
                    texto, falha = cache_textos[referencia]
                    if texto:
                        textos_registros[referencia] = texto
                    elif falha:
                        falhas_textos[referencia] = falha
                    if referencia[0] == "M":
                        if referencia not in cache_atos:
                            try:
                                cache_atos[referencia] = codigos_atos_confirmados(
                                    cliente.buscar_atos_matricula(referencia[1])
                                )
                            except ErroTri7:
                                # O endpoint complementar não é condição para
                                # conferir o livro: em falha, preserva-se a
                                # validação anterior baseada no texto.
                                cache_atos[referencia] = set()
                        atos_confirmados[referencia] = cache_atos[referencia]
                registro["ocorrencias"] = conferir_protocolo(
                    item, protocolo_json, data_esperada, excecoes,
                    textos_registros=textos_registros,
                    falhas_textos=falhas_textos,
                    atos_confirmados=atos_confirmados,
                )
                registro["conferido"] = True
            except ProtocoloTri7NaoEncontrado:
                registro["erro"] = "Protocolo não encontrado na Tri7."
            except ErroTri7 as erro:
                registro["erro"] = str(erro)
        resultados.append(registro)

    atualizacao = _reindexar_registros_alterados(
        alterados, cache_textos, cliente, request, usuario,
    )
    resumo = _resumir_resultados_livro(resultados)
    detalhes_auditoria = {**resumo, "atualizacao": atualizacao, "fonte": fonte}
    if cobertura:
        detalhes_auditoria["cobertura"] = cobertura
    registrar_auditoria(
        request, acao_auditoria, "sucesso", usuario,
        detalhes=detalhes_auditoria,
    )
    retorno = {
        "dataEsperada": data_esperada.isoformat(),
        "protocolos": resultados,
        "resumo": resumo,
        "atualizacao": atualizacao,
        "fonte": fonte,
        "cobertura": cobertura,
    }
    if salvar_rodada:
        retorno.update(_salvar_rodada_livro(retorno, data_esperada, fonte, usuario))
    return retorno

def _reindexar_registros_alterados(
    alterados: set[tuple[str, int]],
    cache_textos: dict[tuple[str, int], tuple[str | None, str | None]],
    cliente,
    request: Request,
    usuario: str,
) -> dict:
    """Regrava no índice de buscas o que o Livro de Protocolos mostrou alterado.

    Fecha a lacuna entre registrar um ato e a busca refletir esse ato: até
    aqui era preciso descobrir à mão quais matrículas mudaram e revisar uma a
    uma. Os textos já baixados para a conferência, tanto de matrículas quanto
    de Registros Auxiliares, são reaproveitados pelo cache desta requisição.

    Uma falha isolada não derruba a conferência: o protocolo continua
    conferido e o número entra na contagem de falhas para nova tentativa.
    """
    relatorio = {
        "matriculas": 0, "matriculasNovas": 0, "matriculasAlteradas": 0,
        "registrosAuxiliares": 0, "registrosAuxiliaresNovos": 0,
        "falhas": 0, "numerosComFalha": [],
    }
    if not alterados:
        return relatorio

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            for tipo, numero in sorted(alterados):
                try:
                    if tipo == "M":
                        texto = (cache_textos.get((tipo, numero)) or (None, None))[0]
                        if texto is None:
                            texto = cliente.buscar_texto_matricula(numero)["texto"]
                        _, novo, alterado, _, _ = _salvar_indice_matricula(cursor, numero, texto)
                        relatorio["matriculas"] += 1
                        relatorio["matriculasNovas"] += int(bool(novo))
                        relatorio["matriculasAlteradas"] += int(bool(alterado))
                    else:
                        texto = (cache_textos.get((tipo, numero)) or (None, None))[0]
                        if texto is None:
                            texto = cliente.buscar_texto_registro_auxiliar(numero)["texto"]
                        _, inserido = _salvar_indice_auxiliar(cursor, numero, texto)
                        relatorio["registrosAuxiliares"] += 1
                        relatorio["registrosAuxiliaresNovos"] += int(bool(inserido))
                except Exception:  # noqa: BLE001
                    relatorio["falhas"] += 1
                    if len(relatorio["numerosComFalha"]) < 20:
                        relatorio["numerosComFalha"].append(f"{tipo}.{numero}")
            registrar_auditoria_cursor(
                cursor, request, "reindexar_pelo_livro_protocolos", "sucesso",
                usuario, detalhes=relatorio,
            )
        conexao.commit()
    return relatorio


@router.post("/analisar", dependencies=[Depends(proteger_csrf)])
async def analisar_livro_protocolos(
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_livro_protocolos")),
):
    try:
        tamanho = int(request.headers.get("content-length", "0") or 0)
        if tamanho > 15_000_000:
            raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
        pdf_bytes = await request.body()
        if len(pdf_bytes) > 15_000_000:
            raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
        if not pdf_bytes.startswith(b"%PDF") or b"%%EOF" not in pdf_bytes[-2048:]:
            raise HTTPException(status_code=422, detail="Envie um arquivo PDF válido.")

        itens_pdf = extrair_protocolos_pdf(pdf_bytes)
        # A data esperada vem da própria folha (data mais frequente entre os
        # "REGISTRADO"); "hoje - 1 dia" só entra como último recurso, se a
        # folha não tiver nenhum registrado com data legível.
        data_esperada = inferir_data_esperada(itens_pdf) or (
            datetime.now(ZoneInfo("America/Sao_Paulo")).date() - timedelta(days=1)
        )

        return _analisar_itens_livro(
            itens_pdf, data_esperada, request, usuario,
            fonte="PDF",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        registrar_auditoria(request, "analisar_livro_protocolos", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível processar o relatório.") from exc


@router.post("/analisar-data", dependencies=[Depends(proteger_csrf)])
def analisar_livro_protocolos_por_data(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("acessar_livro_protocolos")),
):
    try:
        try:
            data_alvo = date.fromisoformat(str(dados.get("data") or ""))
        except ValueError as erro:
            raise HTTPException(status_code=422, detail="Informe uma data válida para a conferência.") from erro
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        if data_alvo > hoje:
            raise HTTPException(status_code=422, detail="A data da conferência não pode estar no futuro.")

        cliente = cliente_tri7()
        janelas = janelas_livro_protocolos(data_alvo)
        respostas = [
            cliente.buscar_livro_protocolos(inicio, fim)
            for inicio, fim in janelas
        ]
        itens = montar_protocolos_do_dia(respostas, data_alvo)
        cobertura = {
            "inicio": min(inicio for inicio, _fim in janelas).isoformat(),
            "fim": data_alvo.isoformat(),
            "dias": sum((fim - inicio).days + 1 for inicio, fim in janelas),
            "consultas": len(janelas),
            "provisoria": True,
        }
        return _analisar_itens_livro(
            itens, data_alvo, request, usuario,
            cliente=cliente,
            acao_auditoria="analisar_livro_protocolos_por_data",
            fonte="TRI7_DATA",
            cobertura=cobertura,
        )
    except HTTPException:
        raise
    except ErroTri7 as exc:
        registrar_auditoria(request, "analisar_livro_protocolos_por_data", "falha", usuario)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        registrar_auditoria(request, "analisar_livro_protocolos_por_data", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível consultar o Livro pela data.") from exc


@router.post("/reprocessar-falhas", dependencies=[Depends(proteger_csrf)])
def reprocessar_falhas_livro(
    dados: dict, request: Request,
    usuario: str = Depends(exigir_permissao("acessar_livro_protocolos")),
):
    try:
        data_alvo = date.fromisoformat(str(dados.get("data") or ""))
    except ValueError as erro:
        raise HTTPException(status_code=422, detail="Data da rodada inválida.") from erro
    itens = dados.get("itens") or []
    if not isinstance(itens, list) or not itens or len(itens) > 500:
        raise HTTPException(status_code=422, detail="Não há falhas válidas para reprocessar.")
    permitidos = {"numero", "numeroFormatado", "data", "nomeApresentante", "status"}
    saneados = [{chave: item.get(chave) for chave in permitidos} for item in itens if isinstance(item, dict)]
    return _analisar_itens_livro(
        saneados, data_alvo, request, usuario,
        acao_auditoria="reprocessar_falhas_livro_protocolos",
        fonte="REPROCESSAMENTO_FALHAS",
    )


@router.get("/rodadas")
def listar_rodadas_livro(
    data_alvo: date = Query(alias="data"),
    _usuario: str = Depends(exigir_permissao("acessar_livro_protocolos")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, fonte, regras_hash, resumo, criado_por, criado_em
                FROM livro_protocolos_rodadas_aeri WHERE data_esperada=%s
                ORDER BY criado_em DESC LIMIT 30""", (data_alvo,),
            )
            return [{**item, "id": str(item["id"]), "criado_em": item["criado_em"].isoformat()} for item in cursor.fetchall()]


def _excecao_json(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "tituloOriginal": item["titulo_original"],
        "naturezaOriginal": item["natureza_original"],
        "criadoPor": item.get("criado_por"),
        "criadoEm": item["criado_em"].isoformat(),
        "ativa": item.get("ativa", True),
        "justificativa": item.get("justificativa"),
        "vigenciaInicio": item.get("vigencia_inicio").isoformat() if item.get("vigencia_inicio") else None,
        "vigenciaFim": item.get("vigencia_fim").isoformat() if item.get("vigencia_fim") else None,
    }


@router.get("/excecoes")
def listar_excecoes_natureza_titulo(
    _usuario: str = Depends(exigir_permissao("acessar_livro_protocolos")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM livro_protocolos_excecoes_natureza_aeri ORDER BY criado_em DESC"
            )
            return [_excecao_json(item) for item in cursor.fetchall()]


@router.post("/excecoes", status_code=201, dependencies=[Depends(proteger_csrf)])
def confirmar_excecao_natureza_titulo(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    titulo_original = str(dados.get("tituloOriginal") or "").strip()
    natureza_original = str(dados.get("naturezaOriginal") or "").strip()
    justificativa = str(
        dados.get("justificativa")
        or "Equivalência confirmada em conferência humana (registro legado)."
    ).strip()[:500]
    try:
        vigencia_inicio = date.fromisoformat(str(dados.get("vigenciaInicio") or date.today()))
        vigencia_fim = date.fromisoformat(str(dados["vigenciaFim"])) if dados.get("vigenciaFim") else None
    except ValueError as erro:
        raise HTTPException(status_code=422, detail="Vigência inválida.") from erro
    if not titulo_original or not natureza_original:
        raise HTTPException(status_code=422, detail="Informe o título e a natureza formal confirmados.")
    titulo_tema = normalizar_tema(titulo_original)
    natureza_tema = normalizar_tema(natureza_original)
    if not titulo_tema or not natureza_tema:
        raise HTTPException(status_code=422, detail="Título ou natureza formal inválidos.")
    if not natureza_permite_excecao(natureza_original):
        raise HTTPException(
            status_code=422,
            detail="Itens auxiliares como Prenotação, Busca e CEP não podem virar equivalência de título.",
        )

    identificador = uuid4()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO livro_protocolos_excecoes_natureza_aeri
                (id, titulo_tema, natureza_tema, titulo_original, natureza_original, criado_por,
                 ativa, justificativa, vigencia_inicio, vigencia_fim, atualizado_por, atualizado_em)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, NOW())
                ON CONFLICT (titulo_tema, natureza_tema) DO UPDATE SET ativa=TRUE,
                justificativa=EXCLUDED.justificativa, vigencia_inicio=EXCLUDED.vigencia_inicio,
                vigencia_fim=EXCLUDED.vigencia_fim, atualizado_por=EXCLUDED.atualizado_por,
                atualizado_em=NOW()
                RETURNING *""",
                (identificador, titulo_tema, natureza_tema, titulo_original, natureza_original,
                 usuario, justificativa, vigencia_inicio, vigencia_fim, usuario),
            )
            item = cursor.fetchone()
            if item is None:
                # Já existia (mesmo par de outro protocolo/usuário) -- devolve a
                # exceção existente em vez de erro, a intenção do clique já foi
                # cumprida antes.
                cursor.execute(
                    """SELECT * FROM livro_protocolos_excecoes_natureza_aeri
                    WHERE titulo_tema=%s AND natureza_tema=%s""",
                    (titulo_tema, natureza_tema),
                )
                item = cursor.fetchone()
            cursor.execute(
                "INSERT INTO livro_protocolos_excecoes_eventos_aeri (excecao_id, tipo, usuario, detalhes) VALUES (%s,'CRIACAO',%s,%s)",
                (item["id"], usuario, Jsonb({"justificativa": justificativa, "vigenciaInicio": vigencia_inicio.isoformat(),
                                             "vigenciaFim": vigencia_fim.isoformat() if vigencia_fim else None})),
            )
            registrar_auditoria_cursor(
                cursor, request, "confirmar_excecao_livro_protocolos", "sucesso",
                usuario,
                detalhes={"titulo": titulo_original, "natureza": natureza_original},
            )
        conexao.commit()
    return _excecao_json(item)


@router.delete("/excecoes/{identificador}", status_code=204, dependencies=[Depends(proteger_csrf)])
def remover_excecao_natureza_titulo(
    identificador: UUID,
    request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE livro_protocolos_excecoes_natureza_aeri SET ativa=FALSE, atualizado_por=%s, atualizado_em=NOW() WHERE id=%s AND ativa=TRUE",
                (usuario, identificador),
            )
            removidos = cursor.rowcount
            if removidos:
                cursor.execute(
                    "INSERT INTO livro_protocolos_excecoes_eventos_aeri (excecao_id, tipo, usuario) VALUES (%s,'DESATIVACAO',%s)",
                    (identificador, usuario),
                )
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Exceção não encontrada.")
    registrar_auditoria(request, "remover_excecao_livro_protocolos", "sucesso", usuario, str(identificador))
    return Response(status_code=204)


@router.post("/excecoes/{identificador}/reativar", dependencies=[Depends(proteger_csrf)])
def reativar_excecao_natureza_titulo(
    identificador: UUID, request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE livro_protocolos_excecoes_natureza_aeri SET ativa=TRUE, atualizado_por=%s, atualizado_em=NOW() WHERE id=%s RETURNING *",
                (usuario, identificador),
            )
            item = cursor.fetchone()
            if item:
                cursor.execute(
                    "INSERT INTO livro_protocolos_excecoes_eventos_aeri (excecao_id, tipo, usuario) VALUES (%s,'REATIVACAO',%s)",
                    (identificador, usuario),
                )
        conexao.commit()
    if not item:
        raise HTTPException(status_code=404, detail="Exceção não encontrada.")
    registrar_auditoria(request, "reativar_excecao_livro_protocolos", "sucesso", usuario, str(identificador))
    return _excecao_json(item)
