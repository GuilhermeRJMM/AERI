from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.registros_auxiliares import (
    extrair_indice_registro_auxiliar,
    normalizar_busca,
    registro_auxiliar_json,
    resumo_certidao_registro_auxiliar,
)
from backend.app.servicos.tri7 import (
    AutenticacaoTri7Falhou,
    ConfiguracaoTri7Invalida,
    ErroTri7,
    RegistroAuxiliarTri7NaoEncontrado,
    RegistroAuxiliarTri7SemTexto,
    cliente_tri7,
    normalizar_numero_matricula,
)


router = APIRouter(
    prefix="/api/registros-auxiliares",
    tags=["registros auxiliares"],
    dependencies=[Depends(preparar_banco)],
)
CHAVE_TRAVA_SINCRONIZACAO = 7_353_801


def _salvar_indice(cursor, numero: int, texto: str) -> tuple[dict, bool]:
    indice = extrair_indice_registro_auxiliar(numero, texto)
    cursor.execute(
        "SELECT texto_hash FROM registros_auxiliares_aeri WHERE numero=%s",
        (numero,),
    )
    anterior = cursor.fetchone()
    alterado = bool(anterior and anterior["texto_hash"] != indice["texto_hash"])
    cursor.execute(
        """INSERT INTO registros_auxiliares_aeri
        (numero, texto_hash, modalidade, situacao, pessoas, nomes_busca, documentos_busca, produtos, safras)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (numero) DO UPDATE SET
            texto_hash=EXCLUDED.texto_hash,
            modalidade=EXCLUDED.modalidade,
            situacao=EXCLUDED.situacao,
            pessoas=EXCLUDED.pessoas,
            nomes_busca=EXCLUDED.nomes_busca,
            documentos_busca=EXCLUDED.documentos_busca,
            produtos=EXCLUDED.produtos,
            safras=EXCLUDED.safras,
            consultado_em=NOW(),
            atualizado_em=CASE
                WHEN registros_auxiliares_aeri.texto_hash <> EXCLUDED.texto_hash THEN NOW()
                ELSE registros_auxiliares_aeri.atualizado_em
            END
        RETURNING *""",
        (
            numero, indice["texto_hash"], indice["modalidade"], indice["situacao"], Jsonb(indice["pessoas"]),
            indice["nomes_busca"], indice["documentos_busca"], Jsonb(indice["produtos"]),
            Jsonb(indice["safras"]),
        ),
    )
    item = cursor.fetchone()
    _limpar_erro(cursor, numero)
    item["alterado"] = alterado
    return item, anterior is None


def _registrar_erro(cursor, numero: int, modo: str, erro: Exception) -> None:
    cursor.execute(
        """INSERT INTO registros_auxiliares_erros_aeri (numero, modo, erro)
        VALUES (%s, %s, %s)
        ON CONFLICT (numero) DO UPDATE SET
            modo=EXCLUDED.modo,
            erro=EXCLUDED.erro,
            tentativas=registros_auxiliares_erros_aeri.tentativas + 1,
            ultima_tentativa_em=NOW()""",
        (numero, modo, str(erro)[:500]),
    )


def _limpar_erro(cursor, numero: int) -> None:
    cursor.execute("DELETE FROM registros_auxiliares_erros_aeri WHERE numero=%s", (numero,))


def _estado_json(cursor) -> dict:
    cursor.execute("SELECT * FROM sincronizacao_registros_auxiliares_aeri WHERE id=1")
    estado = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS total FROM registros_auxiliares_aeri")
    total = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM registros_auxiliares_erros_aeri")
    erros = cursor.fetchone()["total"]
    limite = estado["limite_inicial"]
    concluidos = min(max(estado["proximo_inicial"] - 1, 0), limite)
    return {
        "limiteInicial": limite,
        "proximoInicial": estado["proximo_inicial"],
        "ultimoExistente": estado["ultimo_existente"],
        "proximoRevisao": estado["proximo_revisao"],
        "totalIndexados": total,
        "errosPendentes": erros,
        "progressoInicial": round((concluidos / limite) * 100, 2) if limite else 100,
        "cargaInicialConcluida": estado["proximo_inicial"] > limite,
        "ultimaSincronizacao": (
            estado["ultima_sincronizacao"].isoformat()
            if estado["ultima_sincronizacao"] else None
        ),
    }


@router.get("")
def pesquisar_registros_auxiliares(
    busca: str = "",
    produto: str = "",
    safra: str = "",
    modalidade: str = "",
    limite: int = Query(100, ge=1, le=200),
    _usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    termo = normalizar_busca(busca)[:120]
    documento = "".join(caractere for caractere in busca if caractere.isdigit())[:14]
    produto = normalizar_busca(produto)[:30]
    safra = safra.strip()[:20]
    modalidade = normalizar_busca(modalidade)[:20]
    if not termo or not produto or not safra:
        raise HTTPException(
            status_code=422,
            detail="Informe o nome ou CPF/CNPJ, o produto e a safra.",
        )
    if modalidade not in {"", "PENHOR", "ALIENACAO", "OUTROS"}:
        raise HTTPException(status_code=422, detail="Modalidade inválida.")
    modalidade_banco = "ALIENAÇÃO" if modalidade == "ALIENACAO" else modalidade

    filtros = ["situacao='ATIVO'"]
    parametros = []
    if termo:
        filtros.append("(nomes_busca LIKE %s OR documentos_busca LIKE %s)")
        parametros.extend((f"%{termo}%", f"%{documento or termo}%"))
    if produto:
        filtros.append("produtos ? %s")
        parametros.append(produto)
    if safra:
        filtros.append("safras ? %s")
        parametros.append(safra)
    if modalidade_banco:
        filtros.append("modalidade=%s")
        parametros.append(modalidade_banco)
    where = "WHERE " + " AND ".join(filtros) if filtros else ""
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"""SELECT *, COUNT(*) OVER() AS total_filtrado FROM registros_auxiliares_aeri
                {where} ORDER BY numero DESC LIMIT %s""",
                (*parametros, limite),
            )
            registros = cursor.fetchall()
            total = registros[0]["total_filtrado"] if registros else 0
            itens = [registro_auxiliar_json(item) for item in registros]
            return {
                "itens": itens,
                "resumo": resumo_certidao_registro_auxiliar(total),
            }


@router.get("/status")
def status_sincronizacao(
    _usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            return _estado_json(cursor)


@router.post("/sincronizar", dependencies=[Depends(proteger_csrf)])
def sincronizar_registros_auxiliares(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    modo = str(dados.get("modo", "INICIAL")).strip().upper()
    if modo not in {"INICIAL", "NOVOS", "REVISAO", "ERROS"}:
        raise HTTPException(status_code=422, detail="Modo de sincronização inválido.")
    try:
        tamanho = max(1, min(int(dados.get("tamanho", 15)), 30))
        limite_informado = int(dados.get("limite", 0) or 0)
    except (TypeError, ValueError) as erro:
        raise HTTPException(status_code=422, detail="Parâmetros de sincronização inválidos.") from erro

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s) AS obtida", (CHAVE_TRAVA_SINCRONIZACAO,))
            if not cursor.fetchone()["obtida"]:
                raise HTTPException(status_code=409, detail="Já existe uma sincronização em andamento.")
            try:
                cursor.execute("SELECT * FROM sincronizacao_registros_auxiliares_aeri WHERE id=1")
                estado = cursor.fetchone()
                if limite_informado > estado["limite_inicial"]:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET limite_inicial=%s, ultimo_existente=GREATEST(ultimo_existente,%s), atualizado_em=NOW()
                        WHERE id=1""",
                        (limite_informado, limite_informado),
                    )
                    estado["limite_inicial"] = limite_informado
                    estado["ultimo_existente"] = max(estado["ultimo_existente"], limite_informado)

                if modo == "INICIAL":
                    inicio = estado["proximo_inicial"]
                    fim = min(inicio + tamanho - 1, estado["limite_inicial"])
                    numeros = list(range(inicio, fim + 1)) if inicio <= fim else []
                elif modo == "NOVOS":
                    inicio = estado["ultimo_existente"] + 1
                    numeros = list(range(inicio, inicio + tamanho))
                elif modo == "REVISAO":
                    cursor.execute(
                        """SELECT numero FROM registros_auxiliares_aeri
                        WHERE numero >= %s ORDER BY numero LIMIT %s""",
                        (estado["proximo_revisao"], tamanho),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]
                    if len(numeros) < tamanho:
                        cursor.execute(
                            """SELECT numero FROM registros_auxiliares_aeri
                            WHERE numero < %s ORDER BY numero LIMIT %s""",
                            (estado["proximo_revisao"], tamanho - len(numeros)),
                        )
                        numeros.extend(item["numero"] for item in cursor.fetchall())
                else:
                    cursor.execute(
                        """SELECT numero FROM registros_auxiliares_erros_aeri
                        ORDER BY ultima_tentativa_em ASC, numero ASC LIMIT %s""",
                        (tamanho,),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]

                processados = encontrados = novos = alterados = ausentes = falhas = 0
                erros = []
                ultimo_processado = None
                maior_encontrado = estado["ultimo_existente"]
                falha = None
                for numero in numeros:
                    try:
                        resposta = cliente_tri7().buscar_texto_registro_auxiliar(numero)
                        _item, inserido = _salvar_indice(cursor, numero, resposta["texto"])
                        encontrados += 1
                        novos += int(inserido)
                        alterados += int(_item["alterado"])
                        maior_encontrado = max(maior_encontrado, numero)
                    except (RegistroAuxiliarTri7NaoEncontrado, RegistroAuxiliarTri7SemTexto):
                        _limpar_erro(cursor, numero)
                        ausentes += 1
                    except (ConfiguracaoTri7Invalida, AutenticacaoTri7Falhou) as erro:
                        falha = str(erro)
                        break
                    except ErroTri7 as erro:
                        _registrar_erro(cursor, numero, modo, erro)
                        falhas += 1
                        erros.append({"numero": numero, "erro": str(erro)[:180]})
                    processados += 1
                    ultimo_processado = numero

                if modo == "INICIAL" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET proximo_inicial=GREATEST(proximo_inicial,%s),
                            ultimo_existente=GREATEST(ultimo_existente,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (ultimo_processado + 1, maior_encontrado),
                    )
                elif modo == "NOVOS" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET ultimo_existente=GREATEST(ultimo_existente,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (max(maior_encontrado, ultimo_processado),),
                    )
                elif modo == "REVISAO" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET proximo_revisao=%s, ultima_sincronizacao=NOW(), atualizado_em=NOW()
                        WHERE id=1""",
                        (ultimo_processado + 1,),
                    )
                elif modo == "ERROS" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1"""
                    )

                registrar_auditoria_cursor(
                    cursor, request, "sincronizar_registros_auxiliares", "sucesso", usuario,
                    detalhes={"modo": modo, "processados": processados, "encontrados": encontrados,
                              "novos": novos, "alterados": alterados, "ausentes": ausentes,
                              "falhas": falhas},
                )
                estado_json = _estado_json(cursor)
                conexao.commit()
                return {"modo": modo, "processados": processados, "encontrados": encontrados,
                        "novos": novos, "alterados": alterados, "ausentes": ausentes,
                        "falhas": falhas, "erros": erros, "falha": falha, "estado": estado_json}
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (CHAVE_TRAVA_SINCRONIZACAO,))


@router.get("/{numero}/texto")
def texto_registro_auxiliar(
    numero: int,
    request: Request,
    usuario: str = Depends(exigir_permissao("gerenciar_custas")),
):
    try:
        numero_normalizado = int(normalizar_numero_matricula(numero))
        resposta = cliente_tri7().buscar_texto_registro_auxiliar(numero_normalizado)
    except (RegistroAuxiliarTri7NaoEncontrado, RegistroAuxiliarTri7SemTexto) as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except ConfiguracaoTri7Invalida as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    except ErroTri7 as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            item, _inserido = _salvar_indice(cursor, numero_normalizado, resposta["texto"])
            registrar_auditoria_cursor(
                cursor, request, "consultar_texto_registro_auxiliar", "sucesso", usuario,
                str(numero_normalizado),
            )
        conexao.commit()
    return {"registro": registro_auxiliar_json(item), "texto": resposta["texto"]}
