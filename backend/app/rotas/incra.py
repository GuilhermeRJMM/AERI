import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import preparar_banco
from backend.app.incra import extrair_protocolos, referencias_matriculas_tri7, resumir_protocolo_tri7
from backend.app.seguranca_web import registrar_auditoria
from backend.app.servicos.tri7 import ErroTri7, ProtocoloTri7NaoEncontrado, cliente_tri7


router = APIRouter(tags=["incra"], dependencies=[Depends(preparar_banco)])
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


def _resultado_falha_tri7(situacao: str, rotulo: str, erro: str) -> dict:
    return {
        "situacaoTri7": situacao,
        "situacaoTri7Rotulo": rotulo,
        "cancelado": False,
        "matriculas": [],
        "ultimoAndamento": None,
        "atosVinculadosNaoConfirmados": 0,
        "alertaTri7": None,
        "erroTri7": erro,
    }


@router.post("/analisar-incra", dependencies=[Depends(proteger_csrf)])
async def analisar_incra(request: Request, usuario: str = Depends(exigir_permissao("processar_incra"))):
    try:
        tamanho = int(request.headers.get("content-length", "0") or 0)
        if tamanho > 15_000_000:
            raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
        pdf_bytes = await request.body()
        if len(pdf_bytes) > 15_000_000:
            raise HTTPException(status_code=413, detail="O PDF excede o limite de 15 MB.")
        if not pdf_bytes.startswith(b"%PDF") or b"%%EOF" not in pdf_bytes[-2048:]:
            raise HTTPException(status_code=422, detail="Envie um arquivo PDF válido.")
        resultado = extrair_protocolos(pdf_bytes)
        cliente = cliente_tri7()
        limitador = _LimitadorTaxaTri7(REQUISICOES_POR_SEGUNDO_TRI7)
        consultas = {}
        cache_textos = {}
        for item in resultado["itens"]:
            protocolo = item["protocolo"]
            if protocolo not in consultas:
                limitador.aguardar()
                try:
                    protocolo_json = cliente.buscar_protocolo_completo(protocolo)
                    textos_matriculas = {}
                    falhas_textos = set()
                    for matricula in referencias_matriculas_tri7(protocolo_json):
                        if matricula not in cache_textos:
                            limitador.aguardar()
                            try:
                                resposta = cliente.buscar_texto_matricula(matricula)
                                cache_textos[matricula] = (resposta["texto"], None)
                            except ErroTri7 as erro:
                                cache_textos[matricula] = (None, str(erro))
                        texto, falha = cache_textos[matricula]
                        if texto:
                            textos_matriculas[matricula] = texto
                        elif falha:
                            falhas_textos.add(matricula)
                    consultas[protocolo] = resumir_protocolo_tri7(
                        protocolo_json,
                        textos_matriculas=textos_matriculas,
                        falhas_textos=falhas_textos,
                    )
                except ProtocoloTri7NaoEncontrado:
                    consultas[protocolo] = _resultado_falha_tri7(
                        "NAO_LOCALIZADO", "Não localizado na Tri7",
                        "Protocolo não encontrado na Tri7.",
                    )
                except ErroTri7 as erro:
                    consultas[protocolo] = _resultado_falha_tri7(
                        "CONSULTA_INDISPONIVEL", "Consulta indisponível", str(erro),
                    )
            item.update(consultas[protocolo])

        resultado["consultados_tri7"] = len(consultas)
        resultado["falhas_tri7"] = sum(1 for item in consultas.values() if item["erroTri7"])
        resultado["contagens_tri7"] = {
            situacao: sum(1 for item in consultas.values() if item["situacaoTri7"] == situacao)
            for situacao in (
                "PRATICADO", "CANCELADO_DECURSO_PRAZO", "SEM_ATO",
                "NAO_LOCALIZADO", "CONSULTA_INDISPONIVEL",
            )
        }
        registrar_auditoria(
            request, "analisar_incra", "sucesso", usuario,
            detalhes={
                "protocolos": resultado["protocolos_unicos"],
                "consultadosTri7": resultado["consultados_tri7"],
                "falhasTri7": resultado["falhas_tri7"],
                "canceladosDecurso": resultado["contagens_tri7"]["CANCELADO_DECURSO_PRAZO"],
            },
        )
        return resultado
    except HTTPException:
        raise
    except Exception as exc:
        registrar_auditoria(request, "analisar_incra", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível processar o PDF.") from exc
