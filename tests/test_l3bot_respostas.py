import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.database import preparar_banco
from backend.app.rotas.integracoes import (
    CertidaoRespondida, confirmar_certidao_respondida, router,
)
from tests.test_integracao_custas import conexao_simulada, request


PEDIDO = "S26081052542D"


def dados():
    return CertidaoRespondida(
        eventoId=uuid4(), pedido=PEDIDO,
        respondidoEm=datetime.now(timezone.utc) - timedelta(minutes=1),
        confirmacao="ENVIO_E_FINALIZACAO_SAEC_CONFIRMADOS",
    )


def executar(respostas, evento=None):
    cursor = MagicMock()
    cursor.fetchone.side_effect = respostas
    contexto, con = conexao_simulada(cursor)
    with patch("backend.app.rotas.integracoes.conectar", return_value=contexto), \
            patch("backend.app.rotas.integracoes.registrar_auditoria_cursor"):
        resposta = confirmar_certidao_respondida(
            evento or dados(), request("POST", "/api/integracoes/informar-custas/respondida"),
            usuario="INTEGRACAO_CUSTAS",
        )
    return json.loads(resposta.body), cursor, con


def test_finaliza_e_registra_origem_sem_mudar_resultado_da_busca():
    evento = dados()
    item = {"id": uuid4(), "status": "PAGO_PROCESSANDO", "finalizado": False}
    corpo, cursor, con = executar([{"evento_id": evento.eventoId}, item, {"reaberto": False}], evento)
    assert corpo == {"eventoId": str(evento.eventoId), "pedido": PEDIDO, "situacao": "CONFIRMADO"}
    update = next(c for c in cursor.execute.call_args_list if "SET status='RESPONDIDO'" in c.args[0])
    assert "finalizado=TRUE" in update.args[0]
    assert "finalizado_em=NOW()" in update.args[0]
    assert "resultado=" not in update.args[0]
    historico = next(c for c in cursor.execute.call_args_list if "'CERTIDAO_RESPONDIDA_L3BOT'" in c.args[0])
    assert historico.args[1][2].obj["origem"] == "L3BOT"
    con.commit.assert_called_once()


def test_repeticao_de_evento_nao_consulta_nem_refinaliza_pedido_reaberto():
    evento = dados()
    corpo, cursor, _ = executar([None, {
        "pedido": PEDIDO, "respondido_em": evento.respondidoEm, "situacao": "CONFIRMADO",
    }], evento)
    assert corpo["situacao"] == "CONFIRMADO"
    assert all("custas_livro3_aeri" not in c.args[0] for c in cursor.execute.call_args_list)


def test_mesmo_id_com_outro_pedido_e_recusado():
    evento = dados()
    with pytest.raises(HTTPException) as erro:
        executar([None, {"pedido": "S26081052543D", "respondido_em": evento.respondidoEm}], evento)
    assert erro.value.status_code == 409


@pytest.mark.parametrize("status,finalizado,esperado", [
    ("RESPONDIDO", True, "JA_RESPONDIDO"),
    ("SEM_PAGAMENTO", True, "CONFLITO"),
    ("DUPLICADO_DEVOLVIDO", False, "CONFLITO"),
])
def test_preserva_decisoes_existentes(status, finalizado, esperado):
    corpo, cursor, _ = executar([{"evento_id": uuid4()}, {
        "id": uuid4(), "status": status, "finalizado": finalizado,
    }])
    assert corpo["situacao"] == esperado
    assert all("UPDATE custas_livro3_aeri" not in c.args[0] for c in cursor.execute.call_args_list)


def test_evento_antigo_nao_fecha_reabertura_posterior():
    corpo, cursor, _ = executar([{"evento_id": uuid4()}, {
        "id": uuid4(), "status": "RESPONDIDO", "finalizado": False,
    }, {"reaberto": True}])
    assert corpo["situacao"] == "CONFLITO"
    assert all("UPDATE custas_livro3_aeri" not in c.args[0] for c in cursor.execute.call_args_list)


def test_nao_cria_pedido_que_nao_esta_no_informar_custas():
    corpo, cursor, _ = executar([{"evento_id": uuid4()}, None])
    assert corpo["situacao"] == "NAO_ENCONTRADO"
    assert all("INSERT INTO custas_livro3_aeri" not in c.args[0] for c in cursor.execute.call_args_list)


@pytest.mark.parametrize("alteracao", [
    {"pedido": "12345"}, {"eventoId": "qualquer"}, {"confirmacao": "CLICOU_ENVIAR"},
    {"respondidoEm": "2026-09-16T12:00:00"},
    {"respondidoEm": datetime.now(timezone.utc) + timedelta(days=1)},
    {"status": "RESPONDIDO"},
])
def test_valida_corpo_e_comprovacao(alteracao):
    with pytest.raises(ValidationError):
        CertidaoRespondida.model_validate({**dados().model_dump(), **alteracao})


def test_rota_exige_bearer_sem_aceitar_sessao_como_substituto(monkeypatch):
    monkeypatch.setenv("AERI_CUSTAS_API_TOKEN", "x" * 43)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[preparar_banco] = lambda: None
    with TestClient(app) as cliente:
        for headers in ({}, {"Authorization": "Bearer errado"}):
            resposta = cliente.post("/api/integracoes/informar-custas/respondida",
                                    json=dados().model_dump(mode="json"), headers=headers)
            assert resposta.status_code == 401
