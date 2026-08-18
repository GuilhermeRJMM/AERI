import threading
import time
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.rotas.buscas import _salvar_indice as _salvar_indice_matricula
from backend.app.rotas.registros_auxiliares import _salvar_indice as _salvar_indice_auxiliar
from backend.app.seguranca_web import registrar_auditoria, registrar_auditoria_cursor
from backend.app.servicos.livro_protocolos import (
    conferir_protocolo,
    extrair_protocolos_pdf,
    inferir_data_esperada,
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

# Mesmo limite conservador usado na sincronização de Registros Auxiliares: a
# Tri7 já demonstrou não tolerar bem paralelismo sem controle.
REQUISICOES_POR_SEGUNDO_TRI7 = 3.0


class _LimitadorTaxaTri7:
    def __init__(self, requisicoes_por_segundo: float):
        self._intervalo = 1.0 / requisicoes_por_segundo
        self._proximo = 0.0
        self._trava = threading.Lock()

    def aguardar(self) -> None:
        with self._trava:
            agora = time.monotonic()
            reservado = max(agora, self._proximo)
            self._proximo = reservado + self._intervalo
        espera = reservado - agora
        if espera > 0:
            time.sleep(espera)


def _reindexar_registros_alterados(
    alterados: set[tuple[str, int]],
    cache_textos: dict[tuple[str, int], tuple[str | None, str | None]],
    cliente,
    limitador,
    request: Request,
    usuario: str,
) -> dict:
    """Regrava no índice de buscas o que o Livro de Protocolos mostrou alterado.

    Fecha a lacuna entre registrar um ato e a busca refletir esse ato: até
    aqui era preciso descobrir à mão quais matrículas mudaram e revisar uma a
    uma. As matrículas saem de graça -- o texto já foi baixado para a
    conferência e está no cache; os Registros Auxiliares custam uma consulta
    cada, porque a conferência não precisa do texto deles.

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
                            limitador.aguardar()
                            texto = cliente.buscar_texto_matricula(numero)["texto"]
                        _, novo, alterado, _, _ = _salvar_indice_matricula(cursor, numero, texto)
                        relatorio["matriculas"] += 1
                        relatorio["matriculasNovas"] += int(bool(novo))
                        relatorio["matriculasAlteradas"] += int(bool(alterado))
                    else:
                        limitador.aguardar()
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

        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT titulo_tema, natureza_tema FROM livro_protocolos_excecoes_natureza_aeri")
                excecoes = frozenset((linha["titulo_tema"], linha["natureza_tema"]) for linha in cursor.fetchall())

        cliente = cliente_tri7()
        limitador = _LimitadorTaxaTri7(REQUISICOES_POR_SEGUNDO_TRI7)
        cache_textos: dict[tuple[str, int], tuple[str | None, str | None]] = {}
        # O que o dia efetivamente alterou -- base do reprocessamento do índice.
        alterados: set[tuple[str, int]] = set()
        resultados = []
        for item in itens_pdf:
            registro = {**item, "conferido": False, "ocorrencias": [], "erro": None}
            if item["status"] == "REGISTRADO":
                limitador.aguardar()
                try:
                    protocolo_json = cliente.buscar_protocolo_completo(item["numero"])
                    alterados |= registros_alterados_no_protocolo(protocolo_json)
                    textos_registros = {}
                    falhas_textos = {}
                    for referencia in referencias_textos_protocolo(protocolo_json):
                        if referencia not in cache_textos:
                            limitador.aguardar()
                            try:
                                resposta_texto = cliente.buscar_texto_matricula(referencia[1])
                                cache_textos[referencia] = (resposta_texto["texto"], None)
                            except ErroTri7 as erro:
                                cache_textos[referencia] = (None, str(erro))
                        texto, falha = cache_textos[referencia]
                        if texto:
                            textos_registros[referencia] = texto
                        elif falha:
                            falhas_textos[referencia] = falha
                    registro["ocorrencias"] = conferir_protocolo(
                        item, protocolo_json, data_esperada, excecoes,
                        textos_registros=textos_registros,
                        falhas_textos=falhas_textos,
                    )
                    registro["conferido"] = True
                except ProtocoloTri7NaoEncontrado:
                    registro["erro"] = "Protocolo não encontrado na Tri7."
                except ErroTri7 as erro:
                    registro["erro"] = str(erro)
            resultados.append(registro)

        atualizacao = _reindexar_registros_alterados(
            alterados, cache_textos, cliente, limitador, request, usuario,
        )

        resumo = {
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
        registrar_auditoria(
            request, "analisar_livro_protocolos", "sucesso", usuario,
            detalhes={**resumo, "atualizacao": atualizacao},
        )
        return {
            "dataEsperada": data_esperada.isoformat(),
            "protocolos": resultados,
            "resumo": resumo,
            "atualizacao": atualizacao,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        registrar_auditoria(request, "analisar_livro_protocolos", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível processar o relatório.") from exc


def _excecao_json(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "tituloOriginal": item["titulo_original"],
        "naturezaOriginal": item["natureza_original"],
        "criadoPor": item.get("criado_por"),
        "criadoEm": item["criado_em"].isoformat(),
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
                (id, titulo_tema, natureza_tema, titulo_original, natureza_original, criado_por)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (titulo_tema, natureza_tema) DO NOTHING
                RETURNING *""",
                (identificador, titulo_tema, natureza_tema, titulo_original, natureza_original, usuario),
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
                "DELETE FROM livro_protocolos_excecoes_natureza_aeri WHERE id=%s", (identificador,)
            )
            removidos = cursor.rowcount
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Exceção não encontrada.")
    registrar_auditoria(request, "remover_excecao_livro_protocolos", "sucesso", usuario, str(identificador))
    return Response(status_code=204)
