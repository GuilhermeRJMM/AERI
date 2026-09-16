import json
import sqlite3
from urllib.error import HTTPError

from integracoes.l3bot.l3bot_aeri import IntegracaoAeri


PEDIDO = "S26081052542D"


def estado(fila, evento):
    with sqlite3.connect(fila.caminho) as con:
        return con.execute("SELECT estado FROM respostas WHERE evento_id=?", (evento,)).fetchone()[0]


def liberar_retentativa(fila):
    with sqlite3.connect(fila.caminho) as con:
        con.execute("UPDATE respostas SET proxima_tentativa=0")


def recibo(payload, _token):
    return {"eventoId": payload["eventoId"], "pedido": payload["pedido"], "situacao": "CONFIRMADO"}


def test_intento_sem_prova_nunca_e_enviado(tmp_path):
    enviados = []
    fila = IntegracaoAeri(tmp_path / "fila.db", token="x"*43,
                          transporte=lambda *args: enviados.append(args), avisar=lambda _: None)
    evento = fila.preparar(PEDIDO)
    fila.processar_pendentes()
    assert enviados == []
    assert estado(fila, evento) == "PROVA_PENDENTE"


def test_falha_e_reinicio_preservam_identificador_e_data(tmp_path):
    enviados = []
    def falhar(payload, token):
        enviados.append(payload)
        raise TimeoutError("falha de rede")
    fila = IntegracaoAeri(tmp_path / "fila.db", token="x"*43, transporte=falhar, avisar=lambda _: None)
    evento = fila.preparar(PEDIDO)
    fila.confirmar(evento)
    fila.processar_pendentes()
    assert estado(fila, evento) == "PENDENTE"
    liberar_retentativa(fila)
    def confirmar(payload, token):
        enviados.append(payload)
        return recibo(payload, token)
    reiniciada = IntegracaoAeri(fila.caminho, token="x"*43, transporte=confirmar, avisar=lambda _: None)
    reiniciada.confirmar(evento)
    reiniciada.processar_pendentes()
    assert enviados[0] == enviados[1]
    assert estado(reiniciada, evento) == "CONFIRMADO"
    reiniciada.processar_pendentes()
    assert len(enviados) == 2


def test_recibo_de_outro_pedido_nao_confirma(tmp_path):
    fila = IntegracaoAeri(tmp_path / "fila.db", token="x"*43,
        transporte=lambda p, t: {**recibo(p, t), "pedido": "S26081052543D"}, avisar=lambda _: None)
    evento = fila.preparar(PEDIDO)
    fila.confirmar(evento)
    fila.processar_pendentes()
    assert estado(fila, evento) == "PENDENTE"


def test_conflito_vai_para_revisao_sem_repetir_envio(tmp_path):
    fila = IntegracaoAeri(tmp_path / "fila.db", token="x"*43,
        transporte=lambda p, t: {**recibo(p, t), "situacao": "CONFLITO"}, avisar=lambda _: None)
    evento = fila.preparar(PEDIDO)
    fila.confirmar(evento)
    fila.processar_pendentes()
    assert estado(fila, evento) == "REVISAR"


def test_chave_recusada_nao_expoe_segredo_e_mantem_fila(tmp_path):
    mensagens = []
    segredo = "x"*43
    def recusar(*args):
        raise HTTPError("https://exemplo", 401, segredo, {}, None)
    fila = IntegracaoAeri(tmp_path / "fila.db", token=segredo,
        transporte=recusar, avisar=mensagens.append)
    evento = fila.preparar(PEDIDO)
    fila.confirmar(evento)
    fila.processar_pendentes()
    assert estado(fila, evento) == "PENDENTE"
    assert segredo not in json.dumps(mensagens)


def test_sem_chave_guarda_resposta_sem_rede(tmp_path):
    fila = IntegracaoAeri(tmp_path / "fila.db", token="", transporte=lambda *a: 1/0)
    evento = fila.preparar(PEDIDO)
    fila.confirmar(evento)
    fila.processar_pendentes()
    assert estado(fila, evento) == "PENDENTE"
