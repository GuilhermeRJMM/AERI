import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import preparar_banco
from backend.app.seguranca_web import registrar_auditoria
from backend.app.servicos.livro_protocolos import (
    conferir_protocolo,
    extrair_protocolos_pdf,
    inferir_data_esperada,
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


@router.post("/analisar", dependencies=[Depends(proteger_csrf)])
async def analisar_livro_protocolos(
    request: Request,
    usuario: str = Depends(exigir_permissao("processar_matricula")),
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

        cliente = cliente_tri7()
        limitador = _LimitadorTaxaTri7(REQUISICOES_POR_SEGUNDO_TRI7)
        resultados = []
        for item in itens_pdf:
            registro = {**item, "conferido": False, "ocorrencias": [], "erro": None}
            if item["status"] == "REGISTRADO":
                limitador.aguardar()
                try:
                    protocolo_json = cliente.buscar_protocolo_completo(item["numero"])
                    registro["ocorrencias"] = conferir_protocolo(item, protocolo_json, data_esperada)
                    registro["conferido"] = True
                except ProtocoloTri7NaoEncontrado:
                    registro["erro"] = "Protocolo não encontrado na Tri7."
                except ErroTri7 as erro:
                    registro["erro"] = str(erro)
            resultados.append(registro)

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
        registrar_auditoria(request, "analisar_livro_protocolos", "sucesso", usuario, detalhes=resumo)
        return {"dataEsperada": data_esperada.isoformat(), "protocolos": resultados, "resumo": resumo}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        registrar_auditoria(request, "analisar_livro_protocolos", "falha", usuario)
        raise HTTPException(status_code=422, detail="Não foi possível processar o relatório.") from exc
