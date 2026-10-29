import hmac
import os
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb
from backend.app.servicos.busca_textual import documento_da_consulta, escapar_like

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.executor_presenca import executor_ativo
from backend.app.servicos.custas import revalidar_negativas_custas
from backend.app.servicos.fila_auxiliares import concluir_auxiliar, reagendar_auxiliar
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
JANELA_SONDAGEM_NOVOS = 30
JANELA_LACUNAS_RECENTES = 300
INTERVALO_RECONSULTA_AUSENCIA_HORAS = 24

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
    """Consulta a Tri7 com paralelismo limitado e mantém respostas concluídas.

    Uma falha fatal cancela chamadas que ainda não começaram. As que já
    estavam em trânsito podem terminar e são mantidas para não perder a
    rastreabilidade dos números efetivamente consultados.
    """
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
        if resultado is None or resultado["status"] == "CANCELADO":
            continue
        # As demais requisições do lote podem já estar em trânsito quando
        # chega uma falha fatal. Persistir essas respostas evita perder a
        # rastreabilidade; o cursor sequencial só avança pelo trecho contínuo.
        if resultado["status"] == "FATAL" and falha is None:
            falha = str(resultado["erro"])
        resultados.append(resultado)
    return resultados, falha


def _salvar_indice(cursor, numero: int, texto: str, *, solicitada_ate=None) -> tuple[dict, bool]:
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
    _registrar_consulta_varredura(cursor, numero, "ENCONTRADO")
    if solicitada_ate is not None:
        concluir_auxiliar(cursor, numero, solicitada_ate)
    item["alterado"] = alterado
    return item, anterior is None


def _registrar_erro(cursor, numero: int, modo: str, erro: Exception) -> None:
    cursor.execute(
        """INSERT INTO registros_auxiliares_erros_aeri
        (numero, modo, erro, proxima_tentativa_em)
        VALUES (%s, %s, %s, NOW() + INTERVAL '15 minutes')
        ON CONFLICT (numero) DO UPDATE SET
            modo=EXCLUDED.modo,
            erro=EXCLUDED.erro,
            tentativas=registros_auxiliares_erros_aeri.tentativas + 1,
            ultima_tentativa_em=NOW(),
            proxima_tentativa_em=NOW() + make_interval(mins =>
                LEAST(480, 15 * (1 << LEAST(registros_auxiliares_erros_aeri.tentativas, 5))))""",
        (numero, modo, str(erro)[:500]),
    )
    _registrar_consulta_varredura(cursor, numero, "ERRO")
    reagendar_auxiliar(cursor, numero)


def _registrar_consulta_varredura(cursor, numero: int, resultado: str) -> None:
    """Guarda inclusive 404/sem texto; ausência é rechecável, não terminal."""
    if resultado == "ERRO":
        cursor.execute(
            """INSERT INTO registros_auxiliares_varredura_aeri
            (numero, resultado, consultado_em, proxima_consulta_em, tentativas)
            VALUES (%s, 'ERRO', NOW(), NOW() + INTERVAL '15 minutes', 1)
            ON CONFLICT (numero) DO UPDATE SET
                resultado='ERRO', consultado_em=NOW(),
                tentativas=registros_auxiliares_varredura_aeri.tentativas + 1,
                proxima_consulta_em=NOW() + make_interval(mins =>
                    LEAST(480, 15 * (1 << LEAST(registros_auxiliares_varredura_aeri.tentativas, 5))))""",
            (numero,),
        )
        return
    if resultado == "AUSENTE":
        cursor.execute(
            """INSERT INTO registros_auxiliares_varredura_aeri
            (numero, resultado, consultado_em, proxima_consulta_em, tentativas)
            VALUES (%s, %s, NOW(), NOW() + make_interval(hours => %s), 1)
            ON CONFLICT (numero) DO UPDATE SET
                resultado=EXCLUDED.resultado, consultado_em=NOW(),
                proxima_consulta_em=EXCLUDED.proxima_consulta_em,
                tentativas=registros_auxiliares_varredura_aeri.tentativas + 1""",
            (numero, resultado, INTERVALO_RECONSULTA_AUSENCIA_HORAS),
        )
        return
    cursor.execute(
        """INSERT INTO registros_auxiliares_varredura_aeri
        (numero, resultado, consultado_em, proxima_consulta_em, tentativas)
        VALUES (%s, %s, NOW(), NULL, 0)
        ON CONFLICT (numero) DO UPDATE SET
            resultado=EXCLUDED.resultado, consultado_em=NOW(),
            proxima_consulta_em=NULL, tentativas=0""",
        (numero, resultado),
    )


def _limpar_erro(cursor, numero: int) -> None:
    cursor.execute("DELETE FROM registros_auxiliares_erros_aeri WHERE numero=%s", (numero,))


def _salvar_ausencia(cursor, numero: int) -> None:
    _limpar_erro(cursor, numero)
    _registrar_consulta_varredura(cursor, numero, "AUSENTE")
    # A Tri7 pode publicar o texto depois do lançamento no Livro.
    reagendar_auxiliar(cursor, numero)


def _selecionar_numeros_novos(
    cursor, ultimo_confirmado: int, tamanho: int,
) -> tuple[list[int], int, int]:
    """Sonda adiante do maior registro real e revisita ausências próximas.

    O limite da janela é de sondagem, nunca é gravado como último registro
    existente. Assim um cursor ou faixa vazia não consegue pular garantias.
    """
    tamanho = max(1, tamanho)
    limite = ultimo_confirmado + JANELA_SONDAGEM_NOVOS
    inicio = max(1, ultimo_confirmado - JANELA_LACUNAS_RECENTES)
    quantidade_reconsulta = max(1, (tamanho * 2 + 2) // 3)
    # Uma ausência antiga pode ter sido disponibilizada depois. Também pode
    # haver um número nunca consultado entre dois registros já indexados; a
    # antiga seleção só enxergava ausências conhecidas e ignorava esse buraco.
    cursor.execute(
        """SELECT faixa.numero FROM generate_series(%s::integer, %s::integer) AS faixa(numero)
        LEFT JOIN registros_auxiliares_aeri indice ON indice.numero=faixa.numero
        LEFT JOIN registros_auxiliares_varredura_aeri varredura ON varredura.numero=faixa.numero
        WHERE indice.numero IS NULL
          AND (varredura.numero IS NULL
               OR (varredura.resultado='AUSENTE' AND varredura.proxima_consulta_em<=NOW())
               OR (varredura.resultado='ERRO' AND varredura.proxima_consulta_em<=NOW()))
        ORDER BY CASE WHEN faixa.numero <= %s THEN 0 ELSE 1 END,
                 CASE WHEN varredura.numero IS NULL THEN 0 ELSE 1 END,
                 varredura.consultado_em, faixa.numero LIMIT %s""",
        (inicio, limite, ultimo_confirmado, quantidade_reconsulta),
    )
    reconsultados = [item["numero"] for item in cursor.fetchall()]
    cursor.execute(
        """SELECT COALESCE(MAX(numero), %s) AS maior
        FROM registros_auxiliares_varredura_aeri
        WHERE numero > %s AND numero <= %s""",
        (ultimo_confirmado, ultimo_confirmado, limite),
    )
    maior_sondado = int(cursor.fetchone()["maior"] or ultimo_confirmado)
    quantidade_exploracao = tamanho - len(reconsultados)
    inicio_exploracao = max(ultimo_confirmado + 1, maior_sondado + 1)
    fim_exploracao = min(inicio_exploracao + quantidade_exploracao - 1, limite)
    explorados = (
        list(range(inicio_exploracao, fim_exploracao + 1))
        if quantidade_exploracao > 0 and inicio_exploracao <= fim_exploracao
        else []
    )
    numeros = list(dict.fromkeys([*reconsultados, *explorados]))
    if len(numeros) < tamanho:
        cursor.execute(
            """SELECT faixa.numero FROM generate_series(%s::integer, %s::integer) AS faixa(numero)
            LEFT JOIN registros_auxiliares_aeri indice ON indice.numero=faixa.numero
            LEFT JOIN registros_auxiliares_varredura_aeri varredura ON varredura.numero=faixa.numero
            WHERE indice.numero IS NULL
              AND NOT (faixa.numero = ANY(%s))
              AND (varredura.numero IS NULL
                   OR (varredura.resultado='AUSENTE' AND varredura.proxima_consulta_em<=NOW())
                   OR (varredura.resultado='ERRO' AND varredura.proxima_consulta_em<=NOW()))
            ORDER BY CASE WHEN faixa.numero <= %s THEN 0 ELSE 1 END,
                     CASE WHEN varredura.numero IS NULL THEN 0 ELSE 1 END,
                     varredura.consultado_em, faixa.numero LIMIT %s""",
            (inicio, limite, numeros, ultimo_confirmado, tamanho),
        )
        numeros = list(dict.fromkeys([
            *numeros, *(item["numero"] for item in cursor.fetchall()),
        ]))[:tamanho]
    return numeros, len(reconsultados), len(explorados)


def _selecionar_numeros_lacunas(cursor, inicio: int, limite: int, tamanho: int) -> list[int]:
    """Percorre em círculo todos os números sem texto indexado.

    Números desconhecidos são tentados uma vez. Ausências e falhas técnicas
    só voltam à fila depois do respectivo prazo de retentativa, para não
    gastar toda a varredura circular nos mesmos números inexistentes.
    """
    if limite < 1:
        return []
    inicio = max(1, min(inicio, limite))
    consulta = """SELECT faixa.numero
        FROM generate_series(%s::integer, %s::integer) AS faixa(numero)
        LEFT JOIN registros_auxiliares_aeri indice ON indice.numero=faixa.numero
        LEFT JOIN registros_auxiliares_varredura_aeri varredura ON varredura.numero=faixa.numero
        WHERE indice.numero IS NULL
          AND (varredura.numero IS NULL
               OR (varredura.resultado='AUSENTE'
                   AND varredura.proxima_consulta_em<=NOW())
               OR (varredura.resultado='ERRO'
                   AND varredura.proxima_consulta_em<=NOW()))
        ORDER BY faixa.numero LIMIT %s"""
    cursor.execute(consulta, (inicio, limite, tamanho))
    numeros = [item["numero"] for item in cursor.fetchall()]
    restante = tamanho - len(numeros)
    if restante and inicio > 1:
        cursor.execute(consulta, (1, inicio - 1, restante))
        numeros.extend(item["numero"] for item in cursor.fetchall())
    return numeros


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
    cursor.execute(
        """SELECT COUNT(*) AS total FROM registros_auxiliares_varredura_aeri
        WHERE resultado='AUSENTE'"""
    )
    ausencias_registradas = cursor.fetchone()["total"]
    cursor.execute(
        """SELECT COUNT(*) AS total
        FROM generate_series(%s::integer, %s::integer) AS faixa(numero)
        LEFT JOIN registros_auxiliares_aeri indice ON indice.numero=faixa.numero
        LEFT JOIN registros_auxiliares_varredura_aeri varredura ON varredura.numero=faixa.numero
        WHERE indice.numero IS NULL AND varredura.numero IS NULL""",
        (max(1, estado["ultimo_existente"] - JANELA_LACUNAS_RECENTES),
         max(1, estado["ultimo_existente"])),
    )
    lacunas_recentes_nao_consultadas = cursor.fetchone()["total"]
    limite = estado["limite_inicial"]
    concluidos = min(max(estado["proximo_inicial"] - 1, 0), limite)
    return {
        "limiteInicial": limite,
        "proximoInicial": estado["proximo_inicial"],
        "ultimoExistente": estado["ultimo_existente"],
        "proximoRevisao": estado["proximo_revisao"],
        "proximoLacuna": estado.get("proximo_lacuna", 1),
        "totalIndexados": total,
        "ausenciasRegistradas": ausencias_registradas,
        "lacunasRecentesNaoConsultadas": lacunas_recentes_nao_consultadas,
        "errosPendentes": erros,
        "documentosPendentesReindexacao": hashes_pendentes,
        "progressoInicial": round((concluidos / limite) * 100, 2) if limite else 100,
        "cargaInicialConcluida": estado["proximo_inicial"] > limite,
        "ultimaSincronizacao": (
            estado["ultima_sincronizacao"].isoformat()
            if estado["ultima_sincronizacao"] else None
        ),
        "ultimaSondagemNovos": (
            estado["ultima_sondagem_novos_em"].isoformat()
            if estado["ultima_sondagem_novos_em"] else None
        ),
        "ultimaVarreduraLacunas": (
            estado["ultima_varredura_lacunas_em"].isoformat()
            if estado["ultima_varredura_lacunas_em"] else None
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
    try:
        documento = documento_da_consulta(busca)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    produto = normalizar_busca(produto)[:30]
    safra = normalizar_safra(safra)
    modalidade = normalizar_busca(modalidade)[:20]
    if not termo or not any(c.isalnum() for c in termo):
        raise HTTPException(
            status_code=422,
            detail="Informe o nome ou CPF/CNPJ.",
        )
    if modalidade not in {"", "PENHOR", "ALIENACAO", "OUTROS"}:
        raise HTTPException(status_code=422, detail="Modalidade inválida.")
    modalidade_banco = "ALIENAÇÃO" if modalidade == "ALIENACAO" else modalidade

    filtros = ["situacao='ATIVO'"]
    parametros = []
    if documento:
        filtros.append("documentos_hash ? %s")
        try:
            parametros.append(hash_documento(documento))
        except RuntimeError as erro:
            raise HTTPException(503, "A busca por documento está indisponível nesta configuração.") from erro
    else:
        if len(termo) < 3:
            raise HTTPException(422, "Informe ao menos três caracteres do nome.")
        filtros.append("nomes_busca LIKE %s")
        parametros.append(f"%{escapar_like(termo)}%")
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


@router.get("/diagnostico")
def diagnostico_buscas(
    _usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    from backend.app.database import estatisticas_pool
    from backend.app.servicos.diagnostico_buscas import diagnosticar_cursor
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            dados = diagnosticar_cursor(cursor)
    return {**dados, "poolProcesso": estatisticas_pool()}


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
                        ultimo_existente=GREATEST(ultimo_existente,%s),
                        ultima_sincronizacao=NOW(), atualizado_em=NOW()
                    WHERE id=1""",
                    (numero, numero),
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
                _salvar_ausencia(cursor, numero)
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
                        SET limite_inicial=%s, atualizado_em=NOW()
                        WHERE id=1""",
                        (limite_informado,),
                    )
                    estado["limite_inicial"] = limite_informado

                reconsultadas = exploradas = 0
                if modo == "INICIAL":
                    inicio = estado["proximo_inicial"]
                    fim = min(inicio + tamanho - 1, estado["limite_inicial"])
                    numeros = list(range(inicio, fim + 1)) if inicio <= fim else []
                elif modo == "NOVOS":
                    cursor.execute("SELECT COALESCE(MAX(numero),0) AS maior FROM registros_auxiliares_aeri")
                    ultimo_confirmado = int(cursor.fetchone()["maior"] or 0)
                    estado["ultimo_existente"] = ultimo_confirmado
                    numeros, reconsultadas, exploradas = _selecionar_numeros_novos(
                        cursor, ultimo_confirmado, tamanho,
                    )
                elif modo == "LACUNAS":
                    cursor.execute("SELECT COALESCE(MAX(numero),0) AS maior FROM registros_auxiliares_aeri")
                    ultimo_confirmado = int(cursor.fetchone()["maior"] or 0)
                    limite_lacunas = max(
                        estado["limite_inicial"],
                        ultimo_confirmado + JANELA_SONDAGEM_NOVOS,
                    )
                    numeros = _selecionar_numeros_lacunas(
                        cursor, estado.get("proximo_lacuna", 1), limite_lacunas, tamanho,
                    )
                elif modo == "PRIORITARIA":
                    cursor.execute(
                        """SELECT numero FROM fila_registros_auxiliares_aeri
                        WHERE proxima_tentativa_em<=NOW()
                        ORDER BY solicitada_em, numero LIMIT %s""", (tamanho,),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]
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
                        WHERE proxima_tentativa_em<=NOW()
                        ORDER BY proxima_tentativa_em ASC, ultima_tentativa_em ASC, numero ASC LIMIT %s""",
                        (tamanho,),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]

                # Libera a transação/lock de linha antes da fase lenta: a trava
                # de sincronização (lease em travado_em) já está gravada e
                # commitada, então a conexão fica ociosa durante as chamadas
                # à Tri7 em vez de segurar linhas por até 20s x tamanho do lote.
                conexao.commit()

                solicitada_ate = datetime.now(timezone.utc)
                resultados, falha = _consultar_lote_tri7(numeros)

                processados = encontrados = novos = alterados = ausentes = falhas = 0
                numeros_novos = []
                erros = []
                ultimo_processado = None
                maior_encontrado = estado["ultimo_existente"]
                for resultado in resultados:
                    numero = resultado["numero"]
                    if resultado["status"] == "OK":
                        _item, inserido = _salvar_indice(cursor, numero, resultado["texto"], solicitada_ate=solicitada_ate)
                        encontrados += 1
                        novos += int(inserido)
                        if inserido:
                            numeros_novos.append(numero)
                        alterados += int(_item["alterado"])
                        maior_encontrado = max(maior_encontrado, numero)
                    elif resultado["status"] == "AUSENTE":
                        _salvar_ausencia(cursor, numero)
                        ausentes += 1
                    else:
                        erro = resultado["erro"]
                        _registrar_erro(cursor, numero, modo, erro)
                        falhas += 1
                        erros.append({"numero": numero, "erro": str(erro)[:180]})
                    processados += 1
                    ultimo_processado = numero

                if modo == "INICIAL" and ultimo_processado is not None:
                    processados_por_numero = {item["numero"] for item in resultados}
                    ultimo_contiguo = None
                    for numero in numeros:
                        if numero not in processados_por_numero:
                            break
                        ultimo_contiguo = numero
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET proximo_inicial=GREATEST(proximo_inicial,%s),
                            ultimo_existente=GREATEST(ultimo_existente,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        ((ultimo_contiguo + 1) if ultimo_contiguo is not None else estado["proximo_inicial"],
                         maior_encontrado),
                    )
                elif modo == "NOVOS" and ultimo_processado is not None:
                    maior_real = max(
                        (r["numero"] for r in resultados if r["status"] == "OK"),
                        default=estado["ultimo_existente"],
                    )
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET ultimo_existente=GREATEST(ultimo_existente,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (maior_real,),
                    )
                elif modo == "LACUNAS" and ultimo_processado is not None:
                    proximo_lacuna = 1 if ultimo_processado >= limite_lacunas else ultimo_processado + 1
                    maior_real = max(
                        (r["numero"] for r in resultados if r["status"] == "OK"),
                        default=estado["ultimo_existente"],
                    )
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET ultimo_existente=GREATEST(ultimo_existente,%s), proximo_lacuna=%s,
                            ultima_sincronizacao=NOW(), atualizado_em=NOW()
                        WHERE id=1""",
                        (maior_real, proximo_lacuna),
                    )
                elif modo == "REVISAO" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET proximo_revisao=%s, ultima_sincronizacao=NOW(), atualizado_em=NOW()
                        WHERE id=1""",
                        (ultimo_processado + 1,),
                    )
                elif modo in {"ERROS", "PRIORITARIA"} and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_registros_auxiliares_aeri
                        SET ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1"""
                    )

                if not falha and not falhas and modo in {"NOVOS", "LACUNAS"}:
                    coluna = (
                        "ultima_sondagem_novos_em" if modo == "NOVOS"
                        else "ultima_varredura_lacunas_em"
                    )
                    cursor.execute(
                        f"UPDATE sincronizacao_registros_auxiliares_aeri SET {coluna}=NOW() WHERE id=1"
                    )

                fronteira_conferida = bool(
                    modo == "NOVOS" and ausentes > 0 and falhas == 0 and not falha
                )
                custas_revalidadas = []
                if novos or alterados or fronteira_conferida or (modo == "PRIORITARIA" and encontrados):
                    custas_revalidadas = revalidar_negativas_custas(
                        cursor,
                        usuario,
                        confirmar_pendentes=fronteira_conferida,
                    )

                registrar_auditoria_cursor(
                    cursor, request, "sincronizar_registros_auxiliares", "sucesso", usuario,
                    detalhes={"modo": modo, "processados": processados, "encontrados": encontrados,
                              "novos": novos, "alterados": alterados, "ausentes": ausentes,
                              "falhas": falhas,
                              "custasRevalidadas": len(custas_revalidadas),
                              "fronteiraConferida": fronteira_conferida},
                )
                estado_json = _estado_json(cursor)
                conexao.commit()
                return {"modo": modo, "processados": processados, "encontrados": encontrados,
                        "novos": novos, "alterados": alterados, "ausentes": ausentes,
                        "reconsultadas": reconsultadas, "exploradas": exploradas,
                        "numerosNovos": numeros_novos, "falhas": falhas, "erros": erros,
                        "falha": falha, "estado": estado_json,
                        "custasRevalidadas": custas_revalidadas,
                        "fronteiraConferida": fronteira_conferida}
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
    if modo not in {"INICIAL", "NOVOS", "LACUNAS", "REVISAO", "ERROS"}:
        raise HTTPException(status_code=422, detail="Modo de sincronização inválido.")
    try:
        tamanho = max(1, min(int(dados.get("tamanho", 15)), 30))
        limite_informado = int(dados.get("limite", 0) or 0)
    except (TypeError, ValueError) as erro:
        raise HTTPException(status_code=422, detail="Parâmetros de sincronização inválidos.") from erro
    return _executar_sincronizacao(modo, tamanho, limite_informado, request, usuario)


def _proximo_modo_automatico(cursor) -> str | None:
    cursor.execute(
        """UPDATE sincronizacao_registros_auxiliares_aeri
        SET ciclo_automatico=ciclo_automatico+1 WHERE id=1 RETURNING *"""
    )
    estado = cursor.fetchone()
    ciclo = ("PRIORITARIA", "NOVOS", "REVISAO", "LACUNAS", "PRIORITARIA", "ERROS", "LACUNAS", "REVISAO")
    modo = ciclo[(estado.get("ciclo_automatico", 1) - 1) % len(ciclo)]
    if modo == "PRIORITARIA":
        cursor.execute("SELECT COUNT(*) AS total FROM fila_registros_auxiliares_aeri WHERE proxima_tentativa_em<=NOW()")
        if cursor.fetchone()["total"]:
            return modo
        modo = "REVISAO"
    if estado["proximo_inicial"] <= estado["limite_inicial"]:
        return "INICIAL"
    if modo == "ERROS":
        cursor.execute(
            """SELECT COUNT(*) AS total FROM registros_auxiliares_erros_aeri
            WHERE proxima_tentativa_em<=NOW()"""
        )
        if not cursor.fetchone()["total"]:
            return "LACUNAS"
    return modo


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
