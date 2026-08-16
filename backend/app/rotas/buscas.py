import hmac
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
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


router = APIRouter(
    prefix="/api/buscas",
    tags=["busca de titularidade"],
    dependencies=[Depends(preparar_banco)],
)
LEASE_SEGUNDOS = 300
MAX_WORKERS_TRI7 = 3
MAX_WORKERS_REPROCESSAMENTO = 6
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


def _consultar_lote(
    numeros: list[int], max_workers: int = MAX_WORKERS_TRI7
) -> tuple[list[dict], str | None]:
    if not numeros:
        return [], None
    limitador = _LimitadorTaxa(REQUISICOES_POR_SEGUNDO_TRI7)
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
        COUNT(*) FILTER (WHERE situacao IN ('NAO_ENCONTRADA','SEM_TEXTO','INEXISTENTE')) AS ignoradas
        FROM matriculas_busca_aeri""",
        (HASH_DOCUMENTOS_VERSAO,),
    )
    totais = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS total FROM proprietarios_matriculas_busca_aeri")
    proprietarios = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM matriculas_busca_erros_aeri")
    erros = cursor.fetchone()["total"]
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
        "proximoRevisao": estado["proximo_revisao"],
        "totalIndexadas": totais["total"],
        "matriculasAtivas": totais["ativas"],
        "matriculasEncerradas": totais["encerradas"],
        "matriculasComTexto": totais["com_texto"],
        "documentosPendentesReindexacao": totais["hashes_legados"],
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
                          AND alertas && %s::text[]
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
                        WHERE texto_hash IS NOT NULL
                          AND documentos_hash_versao IS DISTINCT FROM %s
                        ORDER BY numero LIMIT %s""",
                        (HASH_DOCUMENTOS_VERSAO, tamanho),
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
                              "falhas": falhas, "alteradas": alteradas,
                              "auditoriasValidadas": auditorias_validadas,
                              "auditoriasRevisar": auditorias_revisar,
                              "analisesComplementares": complementos_executados},
                )
                estado_json = _estado_json(cursor)
                conexao.commit()
                return {
                    "modo": modo, "processados": processados, "encontradas": encontradas,
                    "ativas": ativas, "encerradas": encerradas, "ausentes": ausentes,
                    "falhas": falhas, "alteradas": alteradas, "erros": erros,
                    "auditoriasValidadas": auditorias_validadas,
                    "auditoriasRevisar": auditorias_revisar,
                    "analisesComplementares": complementos_executados,
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
