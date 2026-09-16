"""Confirma respostas no AERI com fila durável; nunca envia certidões ao SAEC."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


URL_RESPONDIDA = "https://aeri-two.vercel.app/api/integracoes/informar-custas/respondida"
CONFIRMACAO = "ENVIO_E_FINALIZACAO_SAEC_CONFIRMADOS"


def chave_configurada() -> str:
    valor = os.getenv("AERI_CUSTAS_API_TOKEN", "").strip()
    if not valor:
        # Compatibilidade com a instalação já utilizada para informar custas.
        # A atualização não inclui nem imprime a chave existente do operador.
        try:
            from automacoes.custas.tri7_custas.api_catalog import AERI_ACCESS_KEY
            valor = str(AERI_ACCESS_KEY).strip()
        except (ImportError, AttributeError):
            valor = ""
    return valor if 32 <= len(valor) <= 512 else ""


class _SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def enviar_evento(payload: dict, token: str) -> dict:
    requisicao = Request(
        URL_RESPONDIDA, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    with build_opener(_SemRedirecionamento()).open(requisicao, timeout=8) as resposta:
        if resposta.status != 200 or resposta.headers.get_content_type() != "application/json":
            raise ValueError("Resposta inválida da integração")
        corpo = resposta.read(4097)
    if len(corpo) > 4096:
        raise ValueError("Resposta excede limite")
    dados = json.loads(corpo)
    if not isinstance(dados, dict):
        raise ValueError("Resposta inválida da integração")
    return dados


class IntegracaoAeri:
    def __init__(self, caminho: Path, *, token: str | None = None,
                 transporte=enviar_evento, avisar=print):
        self.caminho = Path(caminho)
        self.token = chave_configurada() if token is None else token
        self.transporte = transporte
        self.avisar = avisar
        self._acordar = threading.Event()
        self._parar = threading.Event()
        self._thread = None
        self._processando = threading.Lock()
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._banco() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE IF NOT EXISTS respostas (
                evento_id TEXT PRIMARY KEY, pedido TEXT NOT NULL,
                criado_em TEXT NOT NULL, respondido_em TEXT,
                estado TEXT NOT NULL, tentativas INTEGER NOT NULL DEFAULT 0,
                proxima_tentativa REAL NOT NULL DEFAULT 0,
                ultimo_motivo TEXT NOT NULL DEFAULT '')""")

    @contextmanager
    def _banco(self):
        con = sqlite3.connect(self.caminho, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def preparar(self, pedido: str) -> str:
        """Grava antes do clique. Isto não é prova de resposta nem vai à API."""
        if not re.fullmatch(r"S\d{11}D", pedido):
            raise ValueError("Pedido SAEC inválido")
        evento = str(uuid4())
        with self._banco() as con:
            con.execute(
                "INSERT INTO respostas(evento_id,pedido,criado_em,estado) VALUES(?,?,?,?)",
                (evento, pedido, datetime.now(timezone.utc).isoformat(), "PROVA_PENDENTE"),
            )
        return evento

    def confirmar(self, evento: str) -> None:
        """Chamar somente após sucesso do envio, finalização e pós-condição."""
        with self._banco() as con:
            if not con.execute("SELECT 1 FROM respostas WHERE evento_id=?", (evento,)).fetchone():
                raise ValueError("Evento não preparado")
            con.execute(
                """UPDATE respostas SET estado='PENDENTE', respondido_em=?
                WHERE evento_id=? AND estado='PROVA_PENDENTE'""",
                (datetime.now(timezone.utc).isoformat(), evento),
            )
        self._acordar.set()

    def iniciar(self) -> None:
        if self._thread is not None:
            return
        if not self.token:
            self.avisar("AERI: configure AERI_CUSTAS_API_TOKEN. Respostas ficarão na fila local.")
        with self._banco() as con:
            revisar = con.execute(
                "SELECT COUNT(*) FROM respostas WHERE estado IN ('PROVA_PENDENTE','REVISAR')"
            ).fetchone()[0]
        if revisar:
            self.avisar(f"AERI: {revisar} evento(s) precisam de conferência; consulte a fila local.")
        self._thread = threading.Thread(target=self._executar, name="l3bot-aeri", daemon=True)
        self._thread.start()

    def fechar(self) -> None:
        self._parar.set()
        self._acordar.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _executar(self):
        while not self._parar.is_set():
            self._acordar.clear()
            try:
                self.processar_pendentes()
            except Exception:
                # Nunca expor headers, chaves ou corpo de respostas remotas.
                self.avisar("AERI: sincronização indisponível; a fila será tentada novamente.")
            self._acordar.wait(timeout=30)

    def processar_pendentes(self) -> None:
        if not self.token or not self._processando.acquire(blocking=False):
            return
        try:
            with self._banco() as con:
                pendentes = con.execute(
                    """SELECT * FROM respostas WHERE estado='PENDENTE'
                    AND proxima_tentativa<=? ORDER BY criado_em LIMIT 25""",
                    (time.time(),),
                ).fetchall()
            for evento in pendentes:
                if self._parar.is_set():
                    return
                self._processar(evento)
        finally:
            self._processando.release()

    def _processar(self, evento):
        payload = {
            "eventoId": evento["evento_id"], "pedido": evento["pedido"],
            "respondidoEm": evento["respondido_em"], "confirmacao": CONFIRMACAO,
        }
        estado, motivo = "PENDENTE", "FALHA_TEMPORARIA"
        try:
            resposta = self.transporte(payload, self.token)
            if (resposta.get("eventoId") != payload["eventoId"]
                    or resposta.get("pedido") != payload["pedido"]):
                raise ValueError("Recibo divergente")
            situacao = resposta.get("situacao")
            estados = {"CONFIRMADO": "CONFIRMADO", "JA_RESPONDIDO": "CONFIRMADO",
                       "NAO_ENCONTRADO": "IGNORADO", "CONFLITO": "REVISAR"}
            if situacao not in estados:
                raise ValueError("Situação desconhecida")
            estado, motivo = estados[situacao], situacao
        except HTTPError as erro:
            if erro.code in {409, 422}:
                estado, motivo = "REVISAR", "EVENTO_RECUSADO"
            elif erro.code in {401, 403}:
                motivo = "CREDENCIAL_RECUSADA"
        except Exception:
            pass
        tentativa = evento["tentativas"] + 1
        espera = min(300, 30 * (2 ** min(tentativa - 1, 4)))
        with self._banco() as con:
            con.execute(
                """UPDATE respostas SET estado=?,tentativas=?,proxima_tentativa=?,
                ultimo_motivo=? WHERE evento_id=? AND estado='PENDENTE'""",
                (estado, tentativa, time.time() + espera, motivo, evento["evento_id"]),
            )
        mensagens = {
            "CONFIRMADO": "respondido e finalizado no AERI",
            "IGNORADO": "não está no Informar Custas; nenhuma alteração feita",
            "REVISAR": "precisa de conferência no AERI; nenhuma finalização forçada",
            "PENDENTE": "resposta guardada; aguardando confirmação do AERI",
        }
        self.avisar(f"{evento['pedido']}: {mensagens[estado]}.")


def consultar_fila(caminho: Path):
    """Inspeção local somente leitura, sem chave e sem reenviar certidões."""
    if not caminho.exists():
        print("Nenhuma fila criada nesta instalação.")
        return
    con = sqlite3.connect(caminho.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for row in con.execute(
            "SELECT pedido,estado,tentativas,ultimo_motivo FROM respostas ORDER BY criado_em"
        ):
            print(" | ".join(str(valor) for valor in row))
    finally:
        con.close()


if __name__ == "__main__":
    consultar_fila(Path(__file__).resolve().parent / "dados" / "checkpoints" / "respostas-aeri.sqlite3")
