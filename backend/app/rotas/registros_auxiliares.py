import hmac
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.executor_presenca import executor_ativo
from backend.app.servicos.registros_auxiliares import (
    extrair_indice_registro_auxiliar,
    normalizar_busca,
    normalizar_safra,
    registro_auxiliar_json,
    resumo_certidao_registro_auxiliar,
)
from backend.app.servicos.buscas import HASH_DOCUMENTOS_VERSAO, hash_documento, validar_configuracao_buscas
from backend.app.servicos.tri7 import (
    AutenticacaoTri7Falhou,
    ConfiguracaoTri7Invalida,
    ErroTri7,
    RegistroAuxiliarTri7NaoEncontrado,
    RegistroAuxiliarTri7SemTexto,
    cliente_tri7,
)


router = APIRouter(
    prefix="/api/registros-auxiliares",
    tags=["registros auxiliares"],
    dependencies=[Depends(preparar_banco)],
)
LEASE_SINCRONIZACAO_SEGUNDOS = 300

# Concorrência deliberadamente conservadora: a Tri7 já demonstrou não tolerar
# bem paralelismo sem controle (5 workers sem limite de taxa quebrou em
# produção e foi revertido). Esses valores devem só subir depois de observar
# `errosPendentes` estável por um tempo nesse patamar.
MAX_WORKERS_TRI7 = 3


def _consultar_registro_auxiliar_tri7(
    numero: int, cancelar: threading.Event
) -> dict:
    if cancelar.is_set():
        return {"numero": numero, "status": "CANCELADO"}
    try:
        resposta = cliente_tri7().buscar_texto_registro_auxiliar(numero)
        return {"numero": numero, "status": "OK", "texto": resposta["texto"]}
    except (RegistroAuxiliarTri7NaoEncontrado, RegistroAuxiliarTri7SemTexto):
        return {"numero": numero, "status": "AUSENTE"}
    except (ConfiguracaoTri7Invalida, AutenticacaoTri7Falhou) as erro:
        cancelar.set()
        return {"numero": numero, "status": "FATAL", "erro": erro}
    except ErroTri7 as erro:
        return {"numero": numero, "status": "ERRO", "erro": erro}


def _consultar_lote_tri7(numeros: list[int]) -> tuple[list[dict], str | None]:
    """Consulta a Tri7 com paralelismo limitado, preservando a semântica
    serial: para na primeira falha fatal (autenticação/configuração) sem
    processar nada além dela, mesmo que respostas cheguem fora de ordem."""
    if not numeros:
        return [], None
    cancelar = threading.Event()
    por_numero: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_TRI7, len(numeros))) as executor:
        futuros = {
            executor.submit(_consultar_registro_auxiliar_tri7, numero, cancelar): numero
            for numero in numeros
        }
        for futuro in as_completed(futuros):
            resultado = futuro.result()
            por_numero[resultado["numero"]] = resultado

    resultados = []
    falha = None
    for numero in numeros:
        resultado = por_numero.get(numero)
        if resultado is None or resultado["status"] in ("CANCELADO", "FATAL"):
            if resultado is not None and resultado["status"] == "FATAL":
                falha = str(resultado["erro"])
            break
        resultados.append(resultado)
    return resultados, falha


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
        (numero, texto_hash, modalidade, situacao, pessoas, nomes_busca,
         documentos_busca, documentos_hash, documentos_hash_versao, produtos, safras)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (numero) DO UPDATE SET
            texto_hash=EXCLUDED.texto_hash,
            modalidade=EXCLUDED.modalidade,
            situacao=EXCLUDED.situacao,
            pessoas=EXCLUDED.pessoas,
            nomes_busca=EXCLUDED.nomes_busca,
            documentos_busca=EXCLUDED.documentos_busca,
            documentos_hash=EXCLUDED.documentos_hash,
            documentos_hash_versao=EXCLUDED.documentos_hash_versao,
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
            indice["nomes_busca"], indice["documentos_busca"], Jsonb(indice["documentos_hash"]),
            indice["documentos_hash_versao"], Jsonb(indice["produtos"]),
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
    cursor.execute(
        """SELECT COUNT(*) AS total FROM registros_auxiliares_aeri
        WHERE documentos_hash_versao IS DISTINCT FROM %s""",
        (HASH_DOCUMENTOS_VERSAO,),
    )
    hashes_pendentes = cursor.fetchone()["total"]
    limite = estado["limite_inicial"]
    concluidos = min(max(estado["proximo_inicial"] - 1, 0), limite)
    return {
        "limiteInicial": limite,
        "proximoInicial": estado["proximo_inicial"],
        "ultimoExistente": estado["ultimo_existente"],
        "proximoRevisao": estado["proximo_revisao"],
        "totalIndexados": total,
        "errosPendentes": erros,
        "documentosPendentesReindexacao": hashes_pendentes,
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
    _usuario: str = Depends(exigir_permissao("consultar_registro_auxiliar")),
):
    termo = normalizar_busca(busca)[:120]
    documento = "".join(caractere for caractere in busca if caractere.isdigit())[:14]
    produto = normalizar_busca(produto)[:30]
    safra = normalizar_safra(safra)
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
        # Só filtra por documento quando os dígitos digitados formam um CPF ou
        # CNPJ completo. Antes bastava haver dígito no texto: pesquisar
        # "Ls3 Saran Agropecuária Ltda" extraía o "3" do nome e virava
        # documentos_busca LIKE '%3%', que casa com quase todo documento do
        # acervo -- a busca devolvia dezenas de registros de outras pessoas.
        if len(documento) in {11, 14}:
            filtros.append("(nomes_busca LIKE %s OR documentos_hash ? %s)")
            parametros.extend((f"%{termo}%", hash_documento(documento)))
        else:
            filtros.append("nomes_busca LIKE %s")
            parametros.append(f"%{termo}%")
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
    _usuario: str = Depends(exigir_permissao("consultar_registro_auxiliar")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            return _estado_json(cursor)


@router.get("/erros")
def listar_erros_sincronizacao(
    _usuario: str = Depends(exigir_permissao("revisar_registro_auxiliar")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT numero, modo, erro, tentativas, ultima_tentativa_em
                FROM registros_auxiliares_erros_aeri
                ORDER BY tentativas DESC, ultima_tentativa_em DESC
                LIMIT 200"""
            )
            return [
                {
                    "numero": item["numero"],
                    "modo": item["modo"],
                    "erro": item["erro"],
                    "tentativas": item["tentativas"],
                    "ultimaTentativaEm": item["ultima_tentativa_em"].isoformat(),
                }
                for item in cursor.fetchall()
            ]


@router.get("/lacunas")
def listar_lacunas_registros_auxiliares(
    limite: int = Query(200, ge=1, le=500),
    _usuario: str = Depends(exigir_permissao("revisar_registro_auxiliar")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT numero, situacao, modalidade, pessoas, produtos, safras, consultado_em
                FROM registros_auxiliares_aeri
                WHERE pessoas='[]'::jsonb OR produtos='[]'::jsonb OR safras='[]'::jsonb
                   OR situacao='INDETERMINADO'
                ORDER BY numero DESC LIMIT %s""", (limite,),
            )
            return [{
                "numero": item["numero"], "situacao": item["situacao"],
                "semEmitenteDevedor": not bool(item["pessoas"]),
                "semProduto": not bool(item["produtos"]), "semSafra": not bool(item["safras"]),
                "consultadoEm": item["consultado_em"].isoformat(),
            } for item in cursor.fetchall()]


@router.post("/{numero}/revisar", dependencies=[Depends(proteger_csrf)])
def revisar_registro_auxiliar(
    numero: int,
    request: Request,
    usuario: str = Depends(exigir_permissao("revisar_registro_auxiliar")),
):
    """Reconsulta um único número na Tri7 e regrava o índice na hora, sem
    esperar a fila sequencial de REVISÃO alcançá-lo. Útil quando se sabe que
    um Registro Auxiliar específico acabou de receber uma averbação/
    retificação e não se quer esperar o ciclo diário (ou clicar em "Revisar
    registros indexados" até a fila chegar nele)."""
    if numero <= 0:
        raise HTTPException(status_code=422, detail="Número inválido.")
    try:
        validar_configuracao_buscas()
    except RuntimeError as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro

    resultado = _consultar_registro_auxiliar_tri7(numero, threading.Event())

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if resultado["status"] == "OK":
                item, inserido = _salvar_indice(cursor, numero, resultado["texto"])
                # Ao incluir manualmente um número acima do limite conhecido,
                # amplia a faixa da carga inicial sem avançar o cursor. Assim,
                # a interface reconhece imediatamente o novo limite e a próxima
                # sincronização ainda percorre eventuais registros intermediários.
                cursor.execute(
                    """UPDATE sincronizacao_registros_auxiliares_aeri
                    SET limite_inicial=GREATEST(limite_inicial,%s),
                        ultima_sincronizacao=NOW(), atualizado_em=NOW()
                    WHERE id=1""",
                    (numero,),
                )
                registrar_auditoria_cursor(
                    cursor, request, "revisar_registro_auxiliar", "sucesso", usuario,
                    detalhes={"numero": numero, "novo": inserido, "alterado": item["alterado"]},
                )
                estado = _estado_json(cursor)
                conexao.commit()
                return {
                    "status": "OK", "novo": inserido,
                    "item": registro_auxiliar_json(item), "estado": estado,
                }

            if resultado["status"] == "AUSENTE":
                _limpar_erro(cursor, numero)
                registrar_auditoria_cursor(
                    cursor, request, "revisar_registro_auxiliar", "ausente", usuario, detalhes={"numero": numero},
                )
                conexao.commit()
                raise HTTPException(status_code=404, detail="Registro Auxiliar sem texto disponível na Tri7.")

            erro = resultado.get("erro")
            _registrar_erro(cursor, numero, "MANUAL", erro)
            registrar_auditoria_cursor(
                cursor, request, "revisar_registro_auxiliar", "falha", usuario,
                detalhes={"numero": numero, "erro": str(erro)[:180]},
            )
            conexao.commit()
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a Tri7: {erro}")


def _executar_sincronizacao(
    modo: str, tamanho: int, limite_informado: int, request: Request, usuario: str
) -> dict:
    try:
        validar_configuracao_buscas()
    except RuntimeError as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            # Trava por lease (não por pg_advisory_lock): a trava por sessão
            # depende da conexão nunca morrer sem passar pelo `finally`, o
            # que falha sob pool de conexão ou função serverless encerrada
            # por timeout — nesses casos a trava ficava presa para sempre.
            # Uma trava com expiração se auto-recupera mesmo se o processo
            # for encerrado no meio da sincronização.
            cursor.execute(
                """UPDATE sincronizacao_registros_auxiliares_aeri
                SET travado_em=NOW()
                WHERE id=1 AND (travado_em IS NULL OR travado_em < NOW() - make_interval(secs => %s))
                RETURNING *""",
                (LEASE_SINCRONIZACAO_SEGUNDOS,),
            )
            estado = cursor.fetchone()
            conexao.commit()
            if estado is None:
                raise HTTPException(status_code=409, detail="Já existe uma sincronização em andamento.")
            try:
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
                        WHERE documentos_hash_versao IS DISTINCT FROM %s
                        ORDER BY numero LIMIT %s""",
                        (HASH_DOCUMENTOS_VERSAO, tamanho),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]
                    if not numeros:
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

                # Libera a transação/lock de linha antes da fase lenta: a trava
                # de sincronização (lease em travado_em) já está gravada e
                # commitada, então a conexão fica ociosa durante as chamadas
                # à Tri7 em vez de segurar linhas por até 20s x tamanho do lote.
                conexao.commit()

                resultados, falha = _consultar_lote_tri7(numeros)

                processados = encontrados = novos = alterados = ausentes = falhas = 0
                numeros_novos = []
                erros = []
                ultimo_processado = None
                maior_encontrado = estado["ultimo_existente"]
                for resultado in resultados:
                    numero = resultado["numero"]
                    if resultado["status"] == "OK":
                        _item, inserido = _salvar_indice(cursor, numero, resultado["texto"])
                        encontrados += 1
                        novos += int(inserido)
                        if inserido:
                            numeros_novos.append(numero)
                        alterados += int(_item["alterado"])
                        maior_encontrado = max(maior_encontrado, numero)
                    elif resultado["status"] == "AUSENTE":
                        _limpar_erro(cursor, numero)
                        ausentes += 1
                    else:
                        erro = resultado["erro"]
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
                        (maior_encontrado,),
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
                        "numerosNovos": numeros_novos, "falhas": falhas, "erros": erros,
                        "falha": falha, "estado": estado_json}
            finally:
                conexao.rollback()
                cursor.execute(
                    "UPDATE sincronizacao_registros_auxiliares_aeri SET travado_em=NULL WHERE id=1"
                )
                conexao.commit()


@router.post("/sincronizar", dependencies=[Depends(proteger_csrf)])
def sincronizar_registros_auxiliares(
    dados: dict,
    request: Request,
    usuario: str = Depends(exigir_permissao("sincronizar_registro_auxiliar")),
):
    modo = str(dados.get("modo", "INICIAL")).strip().upper()
    if modo not in {"INICIAL", "NOVOS", "REVISAO", "ERROS"}:
        raise HTTPException(status_code=422, detail="Modo de sincronização inválido.")
    try:
        tamanho = max(1, min(int(dados.get("tamanho", 15)), 30))
        limite_informado = int(dados.get("limite", 0) or 0)
    except (TypeError, ValueError) as erro:
        raise HTTPException(status_code=422, detail="Parâmetros de sincronização inválidos.") from erro
    return _executar_sincronizacao(modo, tamanho, limite_informado, request, usuario)


def _proximo_modo_automatico(cursor) -> str | None:
    cursor.execute("SELECT * FROM sincronizacao_registros_auxiliares_aeri WHERE id=1")
    estado = cursor.fetchone()
    if estado["proximo_inicial"] <= estado["limite_inicial"]:
        return "INICIAL"
    cursor.execute("SELECT COUNT(*) AS total FROM registros_auxiliares_erros_aeri")
    if cursor.fetchone()["total"] > 0:
        return "ERROS"
    return "NOVOS"


def passo_automatico(request=None, usuario: str = "cron") -> dict:
    """Um lote de indexação, escolhendo o modo sozinho.

    Mora aqui, e não no corpo do cron, porque agora tem dois chamadores: o cron
    diário da Vercel e o executor da serventia. Duas cópias derivariam, e a
    diferença apareceria como registro indexado de um jeito de madrugada e de
    outro durante o dia.
    """
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            modo = _proximo_modo_automatico(cursor)

    resultado = _executar_sincronizacao(modo, tamanho=20, limite_informado=0, request=request, usuario=usuario)
    if modo == "NOVOS":
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM registros_auxiliares_erros_aeri")
                sem_erros = cursor.fetchone()["total"] == 0
        if sem_erros:
            resultado["revisao"] = _executar_sincronizacao(
                "REVISAO", tamanho=20, limite_informado=0, request=request, usuario=usuario
            )
    resultado["modo"] = modo
    return resultado


@router.get("/cron")
def cron_sincronizar_registros_auxiliares(request: Request):
    segredo = os.getenv("CRON_SECRET", "")
    autorizacao = request.headers.get("authorization", "")
    if not segredo or not hmac.compare_digest(autorizacao, f"Bearer {segredo}"):
        raise HTTPException(status_code=401, detail="Não autorizado.")

    # O executor da serventia roda o mesmo lote a cada ciclo. Quando ele esta
    # vivo, repetir aqui so gasta CPU cobrada e disputa o lease. Sem batida
    # recente dele, o cron trabalha como sempre trabalhou.
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if executor_ativo(cursor):
                return {"estado": "EXECUTOR_ATIVO", "detalhe": "indexação em curso na serventia"}
    return passo_automatico(request, "cron")
