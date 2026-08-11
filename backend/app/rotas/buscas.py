import hmac
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.buscas import (
    construir_indice_matricula,
    hash_documento,
    normalizar_documento,
    normalizar_nome,
)
from backend.app.servicos.tri7 import (
    AutenticacaoTri7Falhou,
    ConfiguracaoTri7Invalida,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
    cliente_tri7,
)


router = APIRouter(
    prefix="/api/buscas",
    tags=["busca de titularidade"],
    dependencies=[Depends(preparar_banco)],
)
LEASE_SEGUNDOS = 300
MAX_WORKERS_TRI7 = 3
REQUISICOES_POR_SEGUNDO_TRI7 = 3.0


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
    limitador.aguardar()
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


def _consultar_lote(numeros: list[int]) -> tuple[list[dict], str | None]:
    if not numeros:
        return [], None
    limitador = _LimitadorTaxa(REQUISICOES_POR_SEGUNDO_TRI7)
    cancelar = threading.Event()
    por_numero = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_TRI7, len(numeros))) as executor:
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
        (numero, situacao, confianca, quantidade_proprietarios)
        VALUES (%s,%s,'BAIXA',0)
        ON CONFLICT (numero) DO UPDATE SET
            texto_hash=NULL, resultado_hash=NULL, situacao=EXCLUDED.situacao,
            quantidade_proprietarios=0, confianca='BAIXA', consultado_em=NOW(), atualizado_em=NOW()""",
        (numero, status),
    )
    cursor.execute("DELETE FROM proprietarios_matriculas_busca_aeri WHERE matricula_numero=%s", (numero,))
    _limpar_erro(cursor, numero)


def _salvar_indice(cursor, numero: int, texto: str) -> tuple[dict, bool, bool]:
    resultado = analisar_matricula(texto, numero_matricula=str(numero))
    indice = construir_indice_matricula(numero, texto, resultado)
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
         matriculas_sucessoras, quantidade_proprietarios, confianca, motor_versao)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (numero) DO UPDATE SET
            texto_hash=EXCLUDED.texto_hash, resultado_hash=EXCLUDED.resultado_hash,
            situacao=EXCLUDED.situacao, situacao_origem=EXCLUDED.situacao_origem,
            matriculas_sucessoras=EXCLUDED.matriculas_sucessoras,
            quantidade_proprietarios=EXCLUDED.quantidade_proprietarios,
            confianca=EXCLUDED.confianca, motor_versao=EXCLUDED.motor_versao,
            consultado_em=NOW(),
            atualizado_em=CASE
                WHEN matriculas_busca_aeri.texto_hash IS DISTINCT FROM EXCLUDED.texto_hash
                  OR matriculas_busca_aeri.resultado_hash IS DISTINCT FROM EXCLUDED.resultado_hash
                THEN NOW() ELSE matriculas_busca_aeri.atualizado_em END""",
        (
            numero, indice["texto_hash"], indice["resultado_hash"], indice["situacao"],
            indice["situacao_origem"], Jsonb(indice["matriculas_sucessoras"]),
            indice["quantidade_proprietarios"], indice["confianca"], indice["motor_versao"],
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
    _limpar_erro(cursor, numero)
    return indice, novo, alterado


def _estado_json(cursor) -> dict:
    cursor.execute("SELECT * FROM sincronizacao_matriculas_busca_aeri WHERE id=1")
    estado = cursor.fetchone()
    cursor.execute(
        """SELECT COUNT(*) AS total,
        COUNT(*) FILTER (WHERE situacao='ATIVA') AS ativas,
        COUNT(*) FILTER (WHERE situacao='ENCERRADA') AS encerradas,
        COUNT(*) FILTER (WHERE texto_hash IS NOT NULL) AS com_texto,
        COUNT(*) FILTER (WHERE situacao IN ('NAO_ENCONTRADA','SEM_TEXTO','INEXISTENTE')) AS ignoradas
        FROM matriculas_busca_aeri"""
    )
    totais = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS total FROM proprietarios_matriculas_busca_aeri")
    proprietarios = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM matriculas_busca_erros_aeri")
    erros = cursor.fetchone()["total"]
    limite = estado["limite_inicial"]
    concluidos = min(max(estado["proximo_inicial"] - 1, 0), limite)
    return {
        "limiteInicial": limite,
        "proximoInicial": estado["proximo_inicial"],
        "ultimoConhecido": estado["ultimo_conhecido"],
        "proximoRevisao": estado["proximo_revisao"],
        "totalIndexadas": totais["total"],
        "matriculasAtivas": totais["ativas"],
        "matriculasEncerradas": totais["encerradas"],
        "matriculasComTexto": totais["com_texto"],
        "matriculasIgnoradas": totais["ignoradas"],
        "proprietariosAtuais": proprietarios,
        "errosPendentes": erros,
        "progressoInicial": round((concluidos / limite) * 100, 2) if limite else 100,
        "cargaInicialConcluida": estado["proximo_inicial"] > limite,
        "ultimaSincronizacao": estado["ultima_sincronizacao"].isoformat() if estado["ultima_sincronizacao"] else None,
    }


@router.get("")
def pesquisar_titularidade(
    termo: str = Query(..., min_length=3, max_length=300),
    limite: int = Query(100, ge=1, le=200),
    _usuario: str = Depends(exigir_permissao("processar_matricula")),
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
            cursor.execute(
                f"""SELECT m.numero, m.situacao, m.confianca AS confianca_matricula,
                m.consultado_em, p.nome, p.documento_mascarado, p.tipo_documento,
                p.proporcao, p.origem, p.confianca,
                CASE WHEN %s='NOME' AND p.nome_busca=%s THEN 'NOME_EXATO'
                     WHEN %s='DOCUMENTO_EXATO' THEN 'DOCUMENTO_EXATO'
                     ELSE 'NOME_PARCIAL' END AS correspondencia
                FROM proprietarios_matriculas_busca_aeri p
                JOIN matriculas_busca_aeri m ON m.numero=p.matricula_numero
                WHERE m.situacao='ATIVA' AND {filtro}
                ORDER BY
                    CASE WHEN p.nome_busca=%s THEN 0 ELSE 1 END,
                    p.nome, m.numero DESC LIMIT %s""",
                (tipo_busca, normalizar_nome(termo), tipo_busca, *parametros, normalizar_nome(termo), limite),
            )
            itens = cursor.fetchall()
    return {
        "termo": termo.strip(),
        "tipoBusca": tipo_busca,
        "quantidade": len(itens),
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


@router.get("/status")
def status_buscas(_usuario: str = Depends(exigir_permissao("processar_matricula"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            return _estado_json(cursor)


@router.get("/erros")
def listar_erros(_usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
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


def _executar_sincronizacao(modo: str, tamanho: int, limite: int, request: Request, usuario: str) -> dict:
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

                if modo == "INICIAL":
                    inicio = estado["proximo_inicial"]
                    fim = min(inicio + tamanho - 1, estado["limite_inicial"])
                    numeros = list(range(inicio, fim + 1)) if inicio <= fim else []
                elif modo == "NOVOS":
                    inicio = estado["ultimo_conhecido"] + 1
                    numeros = list(range(inicio, inicio + tamanho))
                elif modo == "REVISAO":
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

                resultados, falha_fatal = _consultar_lote(numeros)
                processados = encontradas = ativas = encerradas = ausentes = falhas = alteradas = 0
                ultimo_processado = None
                maior_encontrada = estado["ultimo_conhecido"]
                erros = []
                for resultado in resultados:
                    numero = resultado["numero"]
                    if resultado["status"] == "OK":
                        indice, _novo, alterado = _salvar_indice(cursor, numero, resultado["texto"])
                        encontradas += 1
                        alteradas += int(alterado)
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
                    cursor.execute(
                        """UPDATE sincronizacao_matriculas_busca_aeri
                        SET ultimo_conhecido=GREATEST(ultimo_conhecido,%s),
                            ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""",
                        (max(maior_encontrada, ultimo_processado),),
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
                              "falhas": falhas, "alteradas": alteradas},
                )
                estado_json = _estado_json(cursor)
                conexao.commit()
                return {
                    "modo": modo, "processados": processados, "encontradas": encontradas,
                    "ativas": ativas, "encerradas": encerradas, "ausentes": ausentes,
                    "falhas": falhas, "alteradas": alteradas, "erros": erros,
                    "falha": falha_fatal, "estado": estado_json,
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
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    if numero <= 0:
        raise HTTPException(status_code=422, detail="Número de matrícula inválido.")
    resultados, falha = _consultar_lote([numero])
    if falha:
        raise HTTPException(status_code=502, detail=falha)
    if not resultados:
        raise HTTPException(status_code=502, detail="A Tri7 não concluiu a consulta.")
    resultado = resultados[0]
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            if resultado["status"] == "OK":
                indice, novo, alterado = _salvar_indice(cursor, numero, resultado["texto"])
                cursor.execute(
                    """UPDATE sincronizacao_matriculas_busca_aeri
                    SET limite_inicial=GREATEST(limite_inicial,%s),
                        ultimo_conhecido=GREATEST(ultimo_conhecido,%s),
                        ultima_sincronizacao=NOW(), atualizado_em=NOW() WHERE id=1""", (numero, numero),
                )
                registrar_auditoria_cursor(
                    cursor, request, "revisar_matricula_busca", "sucesso", usuario,
                    detalhes={"numero": numero, "novo": novo, "alterado": alterado,
                              "situacao": indice["situacao"]},
                )
                estado = _estado_json(cursor)
                conexao.commit()
                return {"numero": numero, "novo": novo, "alterado": alterado,
                        "situacao": indice["situacao"], "estado": estado}
            if resultado["status"] in {"NAO_ENCONTRADA", "SEM_TEXTO"}:
                _salvar_ausencia(cursor, numero, resultado["status"])
                conexao.commit()
                raise HTTPException(status_code=404, detail="Matrícula sem texto disponível na Tri7.")
            _registrar_erro(cursor, numero, "MANUAL", resultado["erro"])
            conexao.commit()
            raise HTTPException(status_code=502, detail=f"Falha ao consultar a Tri7: {resultado['erro']}")


def _proximo_modo_automatico(cursor) -> str:
    cursor.execute("SELECT * FROM sincronizacao_matriculas_busca_aeri WHERE id=1")
    estado = cursor.fetchone()
    if estado["proximo_inicial"] <= estado["limite_inicial"]:
        return "INICIAL"
    cursor.execute("SELECT COUNT(*) AS total FROM matriculas_busca_erros_aeri")
    return "ERROS" if cursor.fetchone()["total"] else "NOVOS"


@router.get("/cron")
def cron_buscas(request: Request):
    segredo = os.getenv("CRON_SECRET", "")
    autorizacao = request.headers.get("authorization", "")
    if not segredo or not hmac.compare_digest(autorizacao, f"Bearer {segredo}"):
        raise HTTPException(status_code=401, detail="Não autorizado.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            modo = _proximo_modo_automatico(cursor)
    resultado = _executar_sincronizacao(modo, 30, 0, request, "cron")
    if modo == "NOVOS":
        resultado["revisao"] = _executar_sincronizacao("REVISAO", 30, 0, request, "cron")
    return resultado
