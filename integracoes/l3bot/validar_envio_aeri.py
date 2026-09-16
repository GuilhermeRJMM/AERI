"""Copiar para tests/test_aeri_respostas.py na instalação do L3BOT."""
from unittest.mock import MagicMock

import pytest

from l3bot import (
    ActionPolicy, ATTACHMENT_SENT, FINALIZE_IN_SAEC, SEND_TO_SAEC,
    PywinautoAssistedTri7, SafetyStop,
)
from l3bot_aeri import IntegracaoAeri


def test_execucao_real_inicia_e_fecha_integracao_sem_mexer_na_tela(tmp_path, monkeypatch):
    from l3bot import run_f8_auto_mode, WorkflowState
    import l3bot_aeri
    fila = MagicMock()
    fabrica = MagicMock(return_value=fila)
    monkeypatch.setattr(l3bot_aeri, "IntegracaoAeri", fabrica)
    runner = MagicMock()
    runner.run.return_value = WorkflowState.COMPLETE
    resultado = run_f8_auto_mode(
        desktop_factory=lambda **kwargs: object(),
        checkpoint_path_factory=lambda: tmp_path / "workflow-checkpoint.json",
        recovery_logger_factory=lambda path: None,
        runner_factory=lambda *args, **kwargs: runner,
        auto_open_orders=False,
        print_fn=lambda _: None,
    )
    assert resultado is WorkflowState.COMPLETE
    assert fabrica.call_args.args[0] == tmp_path / "respostas-aeri.sqlite3"
    fila.iniciar.assert_called_once()
    fila.fechar.assert_called_once()


def adaptador():
    tri7 = PywinautoAssistedTri7(object(), "win32", action_policy=ActionPolicy(execute=True))
    tri7.integracao_aeri = MagicMock()
    tri7.integracao_aeri.preparar.return_value = "evento-teste"
    tri7.certificate_printed_and_selected = lambda order: True
    tri7._find_canonical_main_with_retry = lambda **kwargs: object()
    tri7._owned_windows = lambda main, **kwargs: ()
    return tri7


@pytest.mark.parametrize("falha", [SEND_TO_SAEC, ATTACHMENT_SENT, FINALIZE_IN_SAEC])
def test_nao_confirma_se_algum_dialogo_falha(order, falha):
    tri7 = adaptador()
    def aceitar(dialogo):
        if dialogo == falha:
            raise SafetyStop("falha simulada")
    tri7.accept_expected_dialog = aceitar
    with pytest.raises(SafetyStop):
        tri7.send_and_finalize(order)
    assert tri7.submission_succeeded(order) is False
    tri7.integracao_aeri.confirmar.assert_not_called()


def test_somente_confirma_depois_do_sucesso_e_sem_dialogos_pendentes(order):
    tri7 = adaptador()
    tri7.accept_expected_dialog = lambda dialogo: None
    tri7.send_and_finalize(order)
    tri7.integracao_aeri.confirmar.assert_not_called()
    tri7._owned_windows = lambda main, **kwargs: ("pendente",)
    assert tri7.submission_succeeded(order) is False
    tri7.integracao_aeri.confirmar.assert_not_called()
    tri7._owned_windows = lambda main, **kwargs: ()
    assert tri7.submission_succeeded(order) is True
    tri7.integracao_aeri.confirmar.assert_called_once_with("evento-teste")


def test_falha_de_disco_antes_do_envio_nao_clica(order):
    tri7 = adaptador()
    tri7.integracao_aeri.preparar.side_effect = OSError("disco cheio")
    tri7.accept_expected_dialog = MagicMock()
    with pytest.raises(SafetyStop):
        tri7.send_and_finalize(order)
    tri7.accept_expected_dialog.assert_not_called()


def test_recibo_na_fila_real_so_apos_conclusao(order, tmp_path):
    enviados = []
    def transporte(payload, token):
        enviados.append(payload)
        return {"eventoId": payload["eventoId"], "pedido": payload["pedido"], "situacao": "CONFIRMADO"}
    tri7 = adaptador()
    tri7.integracao_aeri = IntegracaoAeri(tmp_path / "fila.db", token="x"*43,
                                        transporte=transporte, avisar=lambda _: None)
    tri7.accept_expected_dialog = lambda dialogo: None
    tri7.send_and_finalize(order)
    tri7.integracao_aeri.processar_pendentes()
    assert enviados == []
    assert tri7.submission_succeeded(order)
    tri7.integracao_aeri.processar_pendentes()
    assert len(enviados) == 1
    assert enviados[0]["pedido"] == order.protocol
    # Reavaliar a pós-condição não cria outro envio ou outro evento.
    assert tri7.submission_succeeded(order)
    tri7.integracao_aeri.processar_pendentes()
    assert len(enviados) == 1
