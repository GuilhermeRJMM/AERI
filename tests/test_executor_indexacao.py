"""A indexação sai do navegador e vai para o executor, sem parar dos dois lados.

A auditoria de 30 dias mostrava 4.605 lotes de matrículas e 2.559 de registros
auxiliares — 68% de tudo que o AERI registra —, quase todos disparados por uma
aba em laço, com picos às 23h, 00h e 01h. Cada lote é CPU cobrada na Vercel.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.app.rotas import buscas, registros_auxiliares
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos import executor_presenca


def banco(retorno=None):
    cur = MagicMock()
    cur.fetchone.return_value = retorno if retorno is not None else {"ativo": False}
    con = MagicMock()
    con.__enter__.return_value = con
    con.cursor.return_value.__enter__.return_value = cur
    return con, cur


class TestPresencaDoExecutor:
    def test_executor_vivo_mas_sem_indexar_nao_dispensa_o_cron(self):
        """A armadilha: presença não é capacidade.

        O executor da serventia pode estar rodando e ainda assim não conseguir
        indexar — falta a chave do índice naquela máquina. Se bastasse estar
        vivo para o cron se abster, a indexação pararia dos dois lados ao mesmo
        tempo, sem erro nenhum: só trabalho que deixa de acontecer.
        """
        _con, cur = banco()
        executor_presenca.executor_ativo(cur)
        sql = " ".join(cur.execute.call_args[0][0].split())
        assert "indexa" in sql, "a consulta precisa exigir capacidade, não só batida"

    def test_indexa_nulo_preserva_o_valor_anterior(self):
        """Ciclo que nem tentou indexar não pode rebaixar a capacidade."""
        con, cur = banco()
        with patch.object(executor_presenca, "conectar", lambda: con):
            executor_presenca.registrar_presenca("C-49", None, None)
        sql = " ".join(cur.execute.call_args[0][0].split())
        assert "COALESCE(%s, executores_aeri.indexa)" in sql


class TestCronSeAbstem:
    def test_cron_de_buscas_nao_trabalha_com_executor_ativo(self, monkeypatch):
        con, _cur = banco({"ativo": True})
        monkeypatch.setattr(buscas, "conectar", lambda: con)
        monkeypatch.setattr(buscas, "executar_manutencao_banco", MagicMock())
        monkeypatch.setattr(buscas, "executor_ativo", lambda cursor: True)
        passo = MagicMock()
        monkeypatch.setattr(buscas, "passo_automatico", passo)
        monkeypatch.setenv("CRON_SECRET", "s3gr3d0")
        pedido = MagicMock()
        pedido.headers.get.return_value = "Bearer s3gr3d0"
        assert buscas.cron_buscas(pedido)["estado"] == "EXECUTOR_ATIVO"
        passo.assert_not_called()

    def test_manutencao_do_banco_acontece_mesmo_assim(self, monkeypatch):
        """Ela é diária, é barata e o executor não a faz."""
        con, _cur = banco({"ativo": True})
        manutencao = MagicMock()
        monkeypatch.setattr(buscas, "conectar", lambda: con)
        monkeypatch.setattr(buscas, "executar_manutencao_banco", manutencao)
        monkeypatch.setattr(buscas, "executor_ativo", lambda cursor: True)
        monkeypatch.setattr(buscas, "passo_automatico", MagicMock())
        monkeypatch.setenv("CRON_SECRET", "s3gr3d0")
        pedido = MagicMock()
        pedido.headers.get.return_value = "Bearer s3gr3d0"
        buscas.cron_buscas(pedido)
        manutencao.assert_called_once()

    def test_cron_trabalha_quando_nao_ha_executor(self, monkeypatch):
        con, _cur = banco({"ativo": False})
        monkeypatch.setattr(registros_auxiliares, "conectar", lambda: con)
        monkeypatch.setattr(registros_auxiliares, "executor_ativo", lambda cursor: False)
        passo = MagicMock(return_value={"modo": "NOVOS"})
        monkeypatch.setattr(registros_auxiliares, "passo_automatico", passo)
        monkeypatch.setenv("CRON_SECRET", "s3gr3d0")
        pedido = MagicMock()
        pedido.headers.get.return_value = "Bearer s3gr3d0"
        registros_auxiliares.cron_sincronizar_registros_auxiliares(pedido)
        passo.assert_called_once()


class TestAuditoriaSemRequisicao:
    def test_trabalho_do_executor_fica_identificado_na_trilha(self):
        """Sem requisição não há IP; inventar um seria pior que dizer de onde veio."""
        cur = MagicMock()
        registrar_auditoria_cursor(cur, None, "sincronizar_busca_titularidade",
                                   "sucesso", "executor")
        assert "executor" in cur.execute.call_args[0][1]

    def test_requisicao_normal_continua_registrando_o_ip(self):
        cur = MagicMock()
        pedido = MagicMock()
        pedido.headers.get.side_effect = lambda nome, padrao="": (
            "203.0.113.7" if nome == "x-forwarded-for" else padrao)
        registrar_auditoria_cursor(cur, pedido, "login", "sucesso", "ADM")
        assert "203.0.113.7" in cur.execute.call_args[0][1]


class TestCapacidadeDoExecutor:
    """O que o executor reporta como capacidade decide se o cron descansa."""

    def passo(self, monkeypatch, efeito):
        from scripts import worker_operacional as executor
        con, cur = banco({"indexacao_pausada": False})
        monkeypatch.setattr(executor, "conectar", lambda: con)
        monkeypatch.setattr(executor, "FONTES_INDEXACAO",
                            (("matriculas", "sincronizacao_matriculas_busca_aeri", efeito),))
        executor._indexacao_avisada.clear()
        return executor.passo_indexacao()

    def test_falta_de_configuracao_nao_e_capacidade(self, monkeypatch):
        """503 é esta máquina não dando conta: o cron precisa continuar."""
        def sem_chave(_pedido, _usuario):
            raise HTTPException(status_code=503, detail="configuração ausente")
        assert self.passo(monkeypatch, sem_chave) is False

    def test_lote_de_outra_pessoa_continua_sendo_capacidade(self, monkeypatch):
        """409 é o lease de quem sincroniza pela tela; a máquina está apta."""
        def ocupado(_pedido, _usuario):
            raise HTTPException(status_code=409, detail="já existe indexação em andamento")
        assert self.passo(monkeypatch, ocupado) is True

    def test_tri7_fora_do_ar_nao_rebaixa_a_maquina(self, monkeypatch):
        """O cron bateria na mesma parede; abrir mão dele não ajudaria."""
        def caiu(_pedido, _usuario):
            raise TimeoutError("sem resposta")
        assert self.passo(monkeypatch, caiu) is True

    def test_lote_processado_e_capacidade(self, monkeypatch):
        assert self.passo(monkeypatch, lambda _p, _u: {"modo": "REVISAO", "processados": 30}) is True
