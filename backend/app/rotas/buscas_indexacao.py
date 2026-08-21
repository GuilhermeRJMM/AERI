"""Indexação das matrículas para a busca por titularidade.

Consulta à Tri7, gravação do índice e controle da sincronização. Fica
separado das rotas porque é infraestrutura: as rotas de pesquisa,
auditoria e sincronização usam estas funções, mas o inverso não ocorre.
"""
import os
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb

from backend.app.analise.contrato import versao_indice_motor
from backend.app.database import conectar
from backend.app.seguranca_web import registrar_auditoria_cursor
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
    limitador_tri7,
)


LEASE_SEGUNDOS = 300
MAX_WORKERS_TRI7 = 3
MAX_WORKERS_REPROCESSAMENTO = 6
REQUISICOES_POR_SEGUNDO_TRI7 = 3.0
JANELA_SONDAGEM_NOVOS = 300
logger = logging.getLogger("aeri.buscas")


class _LimitadorTaxa:
    def __init__(self, requisicoes_por_segundo: float):
        self._intervalo = 1.0 / requisicoes_por_segundo
        self._proximo = 0.0
        self._trava = threading.Lock()

    def aguardar(self) -> None:
        with self._trava:
            agora = time.monotonic()
            reservado = max(agora, self._proximo)
            self._proximo = reservado + self._intervalo
        if reservado > agora:
            time.sleep(reservado - agora)


def _consultar_matricula(numero: int, limitador: _LimitadorTaxa, cancelar: threading.Event) -> dict:
    if cancelar.is_set():
        return {"numero": numero, "status": "CANCELADO"}
    try:
        resposta = cliente_tri7().buscar_texto_matricula(numero)
        return {"numero": numero, "status": "OK", "texto": resposta["texto"]}
    except MatriculaTri7NaoEncontrada:
        return {"numero": numero, "status": "NAO_ENCONTRADA"}
    except MatriculaTri7SemTexto:
        return {"numero": numero, "status": "SEM_TEXTO"}
    except (ConfiguracaoTri7Invalida, AutenticacaoTri7Falhou) as erro:
        cancelar.set()
        return {"numero": numero, "status": "FATAL", "erro": erro}
    except ErroTri7 as erro:
        return {"numero": numero, "status": "ERRO", "erro": erro}


def _consultar_lote(
    numeros: list[int], max_workers: int = MAX_WORKERS_TRI7
) -> tuple[list[dict], str | None]:
    if not numeros:
        return [], None
    limitador = limitador_tri7()
    cancelar = threading.Event()
    por_numero = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(numeros))) as executor:
        futuros = {
            executor.submit(_consultar_matricula, numero, limitador, cancelar): numero
            for numero in numeros
        }
        for futuro in as_completed(futuros):
            resultado = futuro.result()
            por_numero[resultado["numero"]] = resultado

    ordenados = []
    falha_fatal = None
    for numero in numeros:
        resultado = por_numero.get(numero)
        if resultado is None or resultado["status"] == "CANCELADO":
            break
        if resultado["status"] == "FATAL":
            falha_fatal = str(resultado["erro"])
            break
        ordenados.append(resultado)
    return ordenados, falha_fatal


def _limpar_erro(cursor, numero: int) -> None:
    cursor.execute("DELETE FROM matriculas_busca_erros_aeri WHERE numero=%s", (numero,))


def _registrar_erro(cursor, numero: int, modo: str, erro: Exception) -> None:
    cursor.execute(
        """INSERT INTO matriculas_busca_erros_aeri (numero, modo, erro)
        VALUES (%s,%s,%s)
        ON CONFLICT (numero) DO UPDATE SET
            modo=EXCLUDED.modo, erro=EXCLUDED.erro,
            tentativas=matriculas_busca_erros_aeri.tentativas + 1,
            ultima_tentativa_em=NOW()""",
        (numero, modo, str(erro)[:500]),
    )


def _salvar_ausencia(cursor, numero: int, status: str) -> None:
    cursor.execute(
        """INSERT INTO matriculas_busca_aeri
        (numero, situacao, confianca, quantidade_proprietarios, documentos_hash_versao)
        VALUES (%s,%s,'BAIXA',0,%s)
        ON CONFLICT (numero) DO UPDATE SET
            texto_hash=NULL, resultado_hash=NULL, situacao=EXCLUDED.situacao,
            quantidade_proprietarios=0, confianca='BAIXA',
            documentos_hash_versao=EXCLUDED.documentos_hash_versao,
            consultado_em=NOW(), atualizado_em=NOW()""",
        (numero, status, HASH_DOCUMENTOS_VERSAO),
    )
    cursor.execute("DELETE FROM proprietarios_matriculas_busca_aeri WHERE matricula_numero=%s", (numero,))
    cursor.execute("DELETE FROM auditorias_matriculas_aeri WHERE matricula_numero=%s", (numero,))
    _limpar_erro(cursor, numero)


def _salvar_auditoria(cursor, resumo: dict) -> None:
    cursor.execute(
        """INSERT INTO auditorias_matriculas_aeri
        (matricula_numero, resultado_hash, auditoria_hash, estado, prioridade,
         confianca_onus, confianca_cadeia, confianca_imovel, veredito_onus,
         veredito_cadeia, veredito_imovel, alertas, metricas, complemento_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (matricula_numero) DO UPDATE SET
            resultado_hash=EXCLUDED.resultado_hash,
            estado=EXCLUDED.estado, prioridade=EXCLUDED.prioridade,
            confianca_onus=EXCLUDED.confianca_onus,
            confianca_cadeia=EXCLUDED.confianca_cadeia,
            confianca_imovel=EXCLUDED.confianca_imovel,
            veredito_onus=EXCLUDED.veredito_onus,
            veredito_cadeia=EXCLUDED.veredito_cadeia,
            veredito_imovel=EXCLUDED.veredito_imovel,
            alertas=EXCLUDED.alertas, metricas=EXCLUDED.metricas,
            complemento_status=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_status
                ELSE EXCLUDED.complemento_status END,
            complemento_modelo=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_modelo ELSE '' END,
            complemento_diagnostico=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_diagnostico ELSE NULL END,
            complemento_unidades_entrada=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_unidades_entrada ELSE 0 END,
            complemento_unidades_saida=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_unidades_saida ELSE 0 END,
            complemento_tentativas=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_tentativas ELSE 0 END,
            complemento_erro=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_erro ELSE '' END,
            complemento_em=CASE
                WHEN auditorias_matriculas_aeri.auditoria_hash=EXCLUDED.auditoria_hash
                  AND auditorias_matriculas_aeri.complemento_status='CONCLUIDA'
                THEN auditorias_matriculas_aeri.complemento_em ELSE NULL END,
            auditoria_hash=EXCLUDED.auditoria_hash,
            analisado_em=NOW(), atualizado_em=NOW()""",
        (
            resumo["numero"], resumo["resultado_hash"], resumo["auditoria_hash"],
            resumo["estado"], resumo["prioridade"], resumo["confianca_onus"],
            resumo["confianca_cadeia"], resumo["confianca_imovel"],
            resumo["veredito_onus"], resumo["veredito_cadeia"], resumo["veredito_imovel"],
            Jsonb(resumo["alertas"]), Jsonb(resumo["metricas"]), resumo["complemento_status"],
        ),
    )


def _tentar_revisao_complementar(cursor, numero: int, texto: str, resumo: dict) -> bool:
    if resumo["prioridade"] != "P0-CRITICA" or limite_complementar_diario() <= 0:
        return False
    cursor.execute(
        "SELECT complemento_status FROM auditorias_matriculas_aeri WHERE matricula_numero=%s",
        (numero,),
    )
    item = cursor.fetchone()
    if not item or item["complemento_status"] != "PENDENTE":
        return False
    cursor.execute(
        """SELECT COUNT(*) AS total FROM auditorias_matriculas_aeri
        WHERE complemento_status='CONCLUIDA' AND complemento_em >= CURRENT_DATE"""
    )
    if cursor.fetchone()["total"] >= limite_complementar_diario():
        return False
    cursor.execute(
        """UPDATE auditorias_matriculas_aeri
        SET complemento_status='PROCESSANDO', complemento_tentativas=complemento_tentativas+1,
            complemento_erro='', atualizado_em=NOW() WHERE matricula_numero=%s""",
        (numero,),
    )
    try:
        complemento = executar_revisao_complementar(texto, resumo)
        cursor.execute(
            """UPDATE auditorias_matriculas_aeri SET complemento_status='CONCLUIDA',
            complemento_modelo=%s, complemento_diagnostico=%s,
            complemento_unidades_entrada=%s, complemento_unidades_saida=%s,
            complemento_erro='', complemento_em=NOW(), atualizado_em=NOW()
            WHERE matricula_numero=%s""",
            (
                complemento["modelo"], Jsonb(complemento["diagnostico"]),
                complemento["unidades_entrada"], complemento["unidades_saida"], numero,
            ),
        )
    except RuntimeError as erro:
        cursor.execute(
            """UPDATE auditorias_matriculas_aeri SET complemento_status='FALHA',
            complemento_erro=%s, complemento_em=NOW(), atualizado_em=NOW()
            WHERE matricula_numero=%s""",
            (str(erro)[:240], numero),
        )
    return True


def _salvar_indice(
    cursor, numero: int, texto: str, permitir_complemento: bool = False,
) -> tuple[dict, bool, bool, dict, bool]:
    resultado = analisar_matricula(texto, numero_matricula=str(numero))
    indice = construir_indice_matricula(numero, texto, resultado)
    resumo_auditoria = construir_resumo_auditoria(numero, texto, resultado)
    cursor.execute(
        "SELECT texto_hash, resultado_hash FROM matriculas_busca_aeri WHERE numero=%s",
        (numero,),
    )
    anterior = cursor.fetchone()
    novo = anterior is None
    alterado = bool(
        anterior and (
            anterior["texto_hash"] != indice["texto_hash"]
            or anterior["resultado_hash"] != indice["resultado_hash"]
        )
    )
    cursor.execute(
        """INSERT INTO matriculas_busca_aeri
        (numero, texto_hash, resultado_hash, situacao, situacao_origem,
         matriculas_sucessoras, quantidade_proprietarios, confianca, motor_versao,
         documentos_hash_versao)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (numero) DO UPDATE SET
            texto_hash=EXCLUDED.texto_hash, resultado_hash=EXCLUDED.resultado_hash,
            situacao=EXCLUDED.situacao, situacao_origem=EXCLUDED.situacao_origem,
            matriculas_sucessoras=EXCLUDED.matriculas_sucessoras,
            quantidade_proprietarios=EXCLUDED.quantidade_proprietarios,
            confianca=EXCLUDED.confianca, motor_versao=EXCLUDED.motor_versao,
            documentos_hash_versao=EXCLUDED.documentos_hash_versao,
            consultado_em=NOW(),
            atualizado_em=CASE
                WHEN matriculas_busca_aeri.texto_hash IS DISTINCT FROM EXCLUDED.texto_hash
                  OR matriculas_busca_aeri.resultado_hash IS DISTINCT FROM EXCLUDED.resultado_hash
                THEN NOW() ELSE matriculas_busca_aeri.atualizado_em END""",
        (
            numero, indice["texto_hash"], indice["resultado_hash"], indice["situacao"],
            indice["situacao_origem"], Jsonb(indice["matriculas_sucessoras"]),
            indice["quantidade_proprietarios"], indice["confianca"], indice["motor_versao"],
            HASH_DOCUMENTOS_VERSAO,
        ),
    )
    cursor.execute("DELETE FROM proprietarios_matriculas_busca_aeri WHERE matricula_numero=%s", (numero,))
    for proprietario in indice["proprietarios"]:
        cursor.execute(
            """INSERT INTO proprietarios_matriculas_busca_aeri
            (matricula_numero, ordem, nome, nome_busca, documento_hash,
             documento_mascarado, tipo_documento, proporcao, origem, confianca)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                numero, proprietario["ordem"], proprietario["nome"], proprietario["nome_busca"],
                proprietario["documento_hash"], proprietario["documento_mascarado"],
                proprietario["tipo_documento"], proprietario["proporcao"],
                proprietario["origem"], proprietario["confianca"],
            ),
        )
    _salvar_auditoria(cursor, resumo_auditoria)
    complemento_executado = bool(
        permitir_complemento
        and _tentar_revisao_complementar(cursor, numero, texto, resumo_auditoria)
    )
    _limpar_erro(cursor, numero)
    return indice, novo, alterado, resumo_auditoria, complemento_executado


def _estado_json(cursor) -> dict:
    cursor.execute("SELECT * FROM sincronizacao_matriculas_busca_aeri WHERE id=1")
    estado = cursor.fetchone()
    cursor.execute(
        """SELECT COUNT(*) AS total,
        COUNT(*) FILTER (WHERE situacao='ATIVA') AS ativas,
        COUNT(*) FILTER (WHERE situacao='ENCERRADA') AS encerradas,
        COUNT(*) FILTER (WHERE texto_hash IS NOT NULL) AS com_texto,
        COUNT(*) FILTER (
            WHERE texto_hash IS NOT NULL
              AND documentos_hash_versao IS DISTINCT FROM %s
        ) AS hashes_legados,
        COUNT(*) FILTER (
            WHERE texto_hash IS NOT NULL
              AND motor_versao IS DISTINCT FROM %s
        ) AS motor_desatualizado,
        COUNT(*) FILTER (
            WHERE texto_hash IS NOT NULL
              AND (
                  documentos_hash_versao IS DISTINCT FROM %s
                  OR motor_versao IS DISTINCT FROM %s
              )
        ) AS reindexacao_pendente,
        COUNT(*) FILTER (WHERE situacao IN ('NAO_ENCONTRADA','SEM_TEXTO','INEXISTENTE')) AS ignoradas,
        -- Situação que o motor não conseguiu classificar. Não é ativa nem
        -- encerrada, então some das duas contagens -- e era por aí que o
        -- total de encerradas do AERI ficava abaixo do relatório da
        -- serventia. Passa a aparecer na tela.
        COUNT(*) FILTER (WHERE situacao='REVISAR') AS sem_classificacao
        FROM matriculas_busca_aeri""",
        (
            HASH_DOCUMENTOS_VERSAO, versao_indice_motor(),
            HASH_DOCUMENTOS_VERSAO, versao_indice_motor(),
        ),
    )
    totais = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS total FROM proprietarios_matriculas_busca_aeri")
    proprietarios = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM matriculas_busca_erros_aeri")
    erros = cursor.fetchone()["total"]
    cursor.execute(
        """SELECT MAX(numero) AS ultimo_sondado
        FROM matriculas_busca_aeri
        WHERE numero > %s AND numero <= %s""",
        (
            estado["ultimo_conhecido"],
            estado["ultimo_conhecido"] + JANELA_SONDAGEM_NOVOS,
        ),
    )
    ultimo_sondado = cursor.fetchone()["ultimo_sondado"] or estado["ultimo_conhecido"]
    cursor.execute(
        """SELECT COUNT(*) AS total,
        COUNT(*) FILTER (WHERE estado='VALIDADA_AUTOMATICAMENTE') AS validadas,
        COUNT(*) FILTER (WHERE estado='REVISAR') AS revisar,
        COUNT(*) FILTER (WHERE prioridade='P0-CRITICA') AS criticas,
        COUNT(*) FILTER (WHERE complemento_status='PENDENTE') AS complemento_pendente,
        COUNT(*) FILTER (WHERE complemento_status='CONCLUIDA') AS complemento_concluido
        FROM auditorias_matriculas_aeri"""
    )
    auditoria = cursor.fetchone()
    limite = estado["limite_inicial"]
    concluidos = min(max(estado["proximo_inicial"] - 1, 0), limite)
    return {
        "limiteInicial": limite,
        "proximoInicial": estado["proximo_inicial"],
        "ultimoConhecido": estado["ultimo_conhecido"],
        "ultimoSondadoNovos": ultimo_sondado,
        "proximaSondagemNovos": ultimo_sondado + 1,
        "proximoRevisao": estado["proximo_revisao"],
        # Números que o índice já tocou, existindo ou não. Não é o mesmo
        # que matrícula analisada: _salvar_ausencia grava linha também para
        # número que a Tri7 diz não existir, e o acervo tem centenas deles.
        "numerosSondados": totais["total"],
        "matriculasExistentes": totais["total"] - totais["ignoradas"],
        "semClassificacao": totais["sem_classificacao"],
        "totalIndexadas": totais["total"],
        "matriculasAtivas": totais["ativas"],
        "matriculasEncerradas": totais["encerradas"],
        "matriculasComTexto": totais["com_texto"],
        "documentosPendentesReindexacao": totais["hashes_legados"],
        "motorPendenteReindexacao": totais["motor_desatualizado"],
        "reindexacaoPendente": totais["reindexacao_pendente"],
        "matriculasIgnoradas": totais["ignoradas"],
        "proprietariosAtuais": proprietarios,
        "auditoriaTotal": auditoria["total"],
        "auditoriaValidadas": auditoria["validadas"],
        "auditoriaRevisar": auditoria["revisar"],
        "auditoriaCriticas": auditoria["criticas"],
        "complementoPendente": auditoria["complemento_pendente"],
        "complementoConcluido": auditoria["complemento_concluido"],
        "errosPendentes": erros,
        "progressoInicial": round((concluidos / limite) * 100, 2) if limite else 100,
        "cargaInicialConcluida": estado["proximo_inicial"] > limite,
        "ultimaSincronizacao": estado["ultima_sincronizacao"].isoformat() if estado["ultima_sincronizacao"] else None,
    }


def _selecionar_numeros_novos(
    cursor, ultimo_conhecido: int, tamanho: int,
) -> tuple[list[int], int, int]:
    """Reconsulta ausências sem deixar a busca exploratória parada.

    ``ultimo_conhecido`` é a maior matrícula realmente localizada e não
    pode avançar só porque um número foi consultado. Usá-lo como único cursor,
    porém, fazia cada clique sondar eternamente os mesmos 30 números vazios.
    Metade do lote passa a revisitar ausências e a outra metade avança por
    números ainda não sondados, dentro de uma janela limitada.
    """
    tamanho = max(1, tamanho)
    quantidade_reconsulta = max(1, tamanho // 2)
    inicio_reconsulta = max(1, ultimo_conhecido - JANELA_SONDAGEM_NOVOS)
    limite_exploracao = ultimo_conhecido + JANELA_SONDAGEM_NOVOS

    cursor.execute(
        """SELECT numero FROM matriculas_busca_aeri
        WHERE situacao IN ('NAO_ENCONTRADA', 'SEM_TEXTO')
          AND numero BETWEEN %s AND %s
        ORDER BY consultado_em, numero LIMIT %s""",
        (inicio_reconsulta, limite_exploracao, quantidade_reconsulta),
    )
    reconsultados = [item["numero"] for item in cursor.fetchall()]

    cursor.execute(
        """SELECT COALESCE(MAX(numero), %s) AS maior
        FROM matriculas_busca_aeri
        WHERE numero > %s AND numero <= %s""",
        (ultimo_conhecido, ultimo_conhecido, limite_exploracao),
    )
    maior_sondado = int(cursor.fetchone()["maior"] or ultimo_conhecido)
    quantidade_exploracao = tamanho - len(reconsultados)
    inicio_exploracao = max(ultimo_conhecido + 1, maior_sondado + 1)
    fim_exploracao = min(
        inicio_exploracao + quantidade_exploracao - 1,
        limite_exploracao,
    )
    explorados = (
        list(range(inicio_exploracao, fim_exploracao + 1))
        if quantidade_exploracao > 0 and inicio_exploracao <= fim_exploracao
        else []
    )

    numeros = list(dict.fromkeys([*reconsultados, *explorados]))
    if len(numeros) < tamanho:
        # Janela totalmente explorada: o restante acelera o rodízio das
        # ausências em vez de voltar sempre ao mesmo começo por acaso.
        cursor.execute(
            """SELECT numero FROM matriculas_busca_aeri
            WHERE situacao IN ('NAO_ENCONTRADA', 'SEM_TEXTO')
              AND numero BETWEEN %s AND %s
            ORDER BY consultado_em, numero LIMIT %s""",
            (inicio_reconsulta, limite_exploracao, tamanho),
        )
        numeros = list(dict.fromkeys([
            *numeros,
            *(item["numero"] for item in cursor.fetchall()),
        ]))[:tamanho]

    return numeros, len(reconsultados), len(explorados)


def _executar_sincronizacao(modo: str, tamanho: int, limite: int, request: Request, usuario: str) -> dict:
    try:
        validar_configuracao_buscas()
    except RuntimeError as erro:
        raise HTTPException(
            status_code=503,
            detail="Indexação indisponível: configuração de segurança ausente no servidor.",
        ) from erro
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """UPDATE sincronizacao_matriculas_busca_aeri SET travado_em=NOW()
                WHERE id=1 AND (travado_em IS NULL OR travado_em < NOW() - make_interval(secs => %s))
                RETURNING *""",
                (LEASE_SEGUNDOS,),
            )
            estado = cursor.fetchone()
            conexao.commit()
            if estado is None:
                raise HTTPException(status_code=409, detail="Já existe uma indexação de matrículas em andamento.")
            try:
                if limite > estado["limite_inicial"]:
                    cursor.execute(
                        """UPDATE sincronizacao_matriculas_busca_aeri
                        SET limite_inicial=%s, ultimo_conhecido=GREATEST(ultimo_conhecido,%s), atualizado_em=NOW()
                        WHERE id=1""", (limite, limite),
                    )
                    estado["limite_inicial"] = limite
                    estado["ultimo_conhecido"] = max(estado["ultimo_conhecido"], limite)

                reconsultadas = exploradas = 0
                if modo == "INICIAL":
                    inicio = estado["proximo_inicial"]
                    fim = min(inicio + tamanho - 1, estado["limite_inicial"])
                    numeros = list(range(inicio, fim + 1)) if inicio <= fim else []
                elif modo == "NOVOS":
                    numeros, reconsultadas, exploradas = _selecionar_numeros_novos(
                        cursor, estado["ultimo_conhecido"], tamanho,
                    )
                elif modo == "REVISAO":
                    cursor.execute(
                        """SELECT numero FROM matriculas_busca_aeri
                        WHERE texto_hash IS NOT NULL
                          AND (
                              documentos_hash_versao IS DISTINCT FROM %s
                              OR motor_versao IS DISTINCT FROM %s
                          )
                        ORDER BY numero LIMIT %s""",
                        (HASH_DOCUMENTOS_VERSAO, versao_indice_motor(), tamanho),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]
                    if not numeros:
                        cursor.execute(
                            """SELECT numero FROM matriculas_busca_aeri
                            WHERE texto_hash IS NOT NULL AND numero >= %s ORDER BY numero LIMIT %s""",
                            (estado["proximo_revisao"], tamanho),
                        )
                        numeros = [item["numero"] for item in cursor.fetchall()]
                        if len(numeros) < tamanho:
                            cursor.execute(
                                """SELECT numero FROM matriculas_busca_aeri
                                WHERE texto_hash IS NOT NULL AND numero < %s ORDER BY numero LIMIT %s""",
                                (estado["proximo_revisao"], tamanho - len(numeros)),
                            )
                            numeros.extend(item["numero"] for item in cursor.fetchall())
                else:
                    cursor.execute(
                        """SELECT numero FROM matriculas_busca_erros_aeri
                        ORDER BY ultima_tentativa_em, numero LIMIT %s""", (tamanho,),
                    )
                    numeros = [item["numero"] for item in cursor.fetchall()]
                conexao.commit()

                logger.info(
                    "sincronizacao_buscas_inicio modo=%s quantidade=%s de=%s ate=%s "
                    "reconsultadas=%s exploradas=%s",
                    modo,
                    len(numeros),
                    min(numeros) if numeros else None,
                    max(numeros) if numeros else None,
                    reconsultadas,
                    exploradas,
                )

                resultados, falha_fatal = _consultar_lote(numeros)
                processados = encontradas = ativas = encerradas = ausentes = falhas = alteradas = 0
                auditorias_validadas = auditorias_revisar = complementos_executados = 0
                try:
                    max_complementos_lote = max(
                        0, min(int(os.getenv("AERI_REVISAO_COMPLEMENTAR_MAX_LOTE", "1")), 3)
                    )
                except ValueError:
                    max_complementos_lote = 0
                ultimo_processado = None
                maior_encontrada = estado["ultimo_conhecido"]
                erros = []
                for resultado in resultados:
                    numero = resultado["numero"]
                    if resultado["status"] == "OK":
                        indice, _novo, alterado, auditoria, complemento_executado = _salvar_indice(
                            cursor, numero, resultado["texto"],
                            permitir_complemento=complementos_executados < max_complementos_lote,
                        )
                        encontradas += 1
                        alteradas += int(alterado)
                        auditorias_validadas += int(auditoria["estado"] == "VALIDADA_AUTOMATICAMENTE")
                        auditorias_revisar += int(auditoria["estado"] == "REVISAR")
                        complementos_executados += int(complemento_executado)
                        ativas += int(indice["situacao"] == "ATIVA")
                        encerradas += int(indice["situacao"] == "ENCERRADA")
                        maior_encontrada = max(maior_encontrada, numero)
                    elif resultado["status"] in {"NAO_ENCONTRADA", "SEM_TEXTO"}:
                        _salvar_ausencia(cursor, numero, resultado["status"])
                        ausentes += 1
                    else:
                        _registrar_erro(cursor, numero, modo, resultado["erro"])
                        falhas += 1
                        erros.append({"numero": numero, "erro": str(resultado["erro"])[:180]})
                    processados += 1
                    ultimo_processado = numero

                if modo == "INICIAL" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_matriculas_busca_aeri
                        SET proximo_inicial=GREATEST(proximo_inicial,%s),
                            ultimo_conhecido=GREATEST(ultimo_conhecido,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (ultimo_processado + 1, maior_encontrada),
                    )
                elif modo == "NOVOS" and ultimo_processado is not None:
                    # Avança só até a maior matrícula REALMENTE encontrada,
                    # e não até o último número sondado.
                    #
                    # Sondar de 39.856 a 39.885 quando o acervo vai só até
                    # 39.869 é normal: o modo procura adiante justamente
                    # para descobrir onde termina. Mas gravar 39.885 como
                    # conhecido faria a próxima sonda começar em 39.886 --
                    # e as matrículas 39.870 a 39.885, quando fossem
                    # abertas, nunca mais seriam indexadas. Some matrícula
                    # do índice sem ninguém perceber.
                    #
                    # Re-sondar alguns números ausentes a cada rodada custa
                    # umas poucas consultas; perder matrícula não tem
                    # conserto automático.
                    cursor.execute(
                        """UPDATE sincronizacao_matriculas_busca_aeri
                        SET ultimo_conhecido=GREATEST(ultimo_conhecido,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (maior_encontrada,),
                    )
                elif modo == "REVISAO" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_matriculas_busca_aeri SET proximo_revisao=%s,
                        ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (ultimo_processado + 1,),
                    )
                elif modo == "ERROS" and ultimo_processado is not None:
                    cursor.execute(
                        """UPDATE sincronizacao_matriculas_busca_aeri
                        SET ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1"""
                    )

                registrar_auditoria_cursor(
                    cursor, request, "sincronizar_busca_titularidade", "sucesso", usuario,
                    detalhes={"modo": modo, "processados": processados, "encontradas": encontradas,
                              "ativas": ativas, "encerradas": encerradas, "ausentes": ausentes,
                              "falhas": falhas, "alteradas": alteradas,
                              "auditoriasValidadas": auditorias_validadas,
                              "auditoriasRevisar": auditorias_revisar,
                              "analisesComplementares": complementos_executados},
                )
                estado_json = _estado_json(cursor)
                conexao.commit()
                logger.log(
                    logging.WARNING if falha_fatal or falhas else logging.INFO,
                    "sincronizacao_buscas_fim modo=%s processadas=%s encontradas=%s "
                    "ausentes=%s falhas=%s falha_fatal=%s",
                    modo, processados, encontradas, ausentes, falhas, bool(falha_fatal),
                )
                return {
                    "modo": modo, "processados": processados, "encontradas": encontradas,
                    "ativas": ativas, "encerradas": encerradas, "ausentes": ausentes,
                    "falhas": falhas, "alteradas": alteradas, "erros": erros,
                    "reconsultadas": reconsultadas, "exploradas": exploradas,
                    "sondagemInicio": min(numeros) if numeros else None,
                    "sondagemFim": max(numeros) if numeros else None,
                    "auditoriasValidadas": auditorias_validadas,
                    "auditoriasRevisar": auditorias_revisar,
                    "analisesComplementares": complementos_executados,
                    "falha": falha_fatal, "estado": estado_json,
                }
            finally:
                conexao.rollback()
                cursor.execute("UPDATE sincronizacao_matriculas_busca_aeri SET travado_em=NULL WHERE id=1")
                conexao.commit()


def _proximo_modo_automatico(cursor) -> str:
    cursor.execute("SELECT * FROM sincronizacao_matriculas_busca_aeri WHERE id=1")
    estado = cursor.fetchone()
    if estado["proximo_inicial"] <= estado["limite_inicial"]:
        return "INICIAL"
    cursor.execute("SELECT COUNT(*) AS total FROM matriculas_busca_erros_aeri")
    return "ERROS" if cursor.fetchone()["total"] else "NOVOS"
