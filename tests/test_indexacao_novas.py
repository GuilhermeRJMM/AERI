"""O modo NOVOS não pode pular matrícula que ainda vai existir.

Ele sonda adiante do último conhecido para descobrir onde o acervo
termina. Gravar como conhecido o último número SONDADO, e não o último
ENCONTRADO, faz a próxima rodada começar depois de uma faixa que ainda
está vazia -- e quando essas matrículas forem abertas, nenhuma rodada
volta para pegá-las. Some matrícula do índice, sem erro nenhum.
"""
import unittest
from unittest.mock import MagicMock, patch

from backend.app.rotas import buscas_indexacao as I


def _conexao(cursor):
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao


class TesteAvancoDoUltimoConhecido(unittest.TestCase):
    """Acervo real vai até 39.869; a sonda cobre até 39.885."""

    ULTIMO_CONHECIDO = 39855
    EXISTENTES = set(range(39856, 39870))

    def _rodar(self, tamanho=30):
        estado = {
            "id": 1, "proximo_inicial": 39856, "limite_inicial": 39855,
            "ultimo_conhecido": self.ULTIMO_CONHECIDO, "proximo_revisao": 1,
        }
        cursor = MagicMock()
        cursor.fetchone.return_value = estado
        cursor.fetchall.return_value = []

        def lote(numeros):
            return ([
                {"numero": n, "status": "OK", "texto": f"m{n}"} if n in self.EXISTENTES
                else {"numero": n, "status": "NAO_ENCONTRADA"}
                for n in numeros
            ], None)

        with patch.object(I, "conectar", return_value=_conexao(cursor)), \
                patch.object(I, "validar_configuracao_buscas"), \
                patch.object(I, "_consultar_lote", side_effect=lote), \
                patch.object(I, "_salvar_indice", return_value=(
                    {"situacao": "ATIVA"}, True, False,
                    {"estado": "VALIDADA_AUTOMATICAMENTE"}, False)), \
                patch.object(I, "_salvar_ausencia"), \
                patch.object(I, "_estado_json", return_value={}), \
                patch.object(I, "registrar_auditoria_cursor"):
            I._executar_sincronizacao("NOVOS", tamanho, 0, MagicMock(), "TESTE")

        # O UPDATE do modo NOVOS é o que grava ultimo_conhecido.
        for chamada in cursor.execute.call_args_list:
            sql = chamada.args[0]
            if "SET ultimo_conhecido=GREATEST" in sql and "proximo_inicial" not in sql:
                return chamada.args[1][0]
        self.fail("o UPDATE de ultimo_conhecido não foi executado")

    def test_grava_a_maior_encontrada_e_nao_a_maior_sondada(self):
        gravado = self._rodar()
        self.assertEqual(
            gravado, 39869,
            "gravar 39.885 faria a próxima sonda começar em 39.886 e as "
            "matrículas 39.870 a 39.885 nunca seriam indexadas",
        )

    def test_a_faixa_ainda_vazia_continua_sendo_sondada(self):
        # Depois da rodada, o próximo início tem de cobrir de novo o que
        # ainda não existe.
        proximo_inicio = self._rodar() + 1
        self.assertLessEqual(proximo_inicio, 39870)


class TesteFalhaFatalNaoPassaPorSucesso(unittest.TestCase):
    def test_lote_cancelado_nao_avanca_o_ponteiro(self):
        # Autenticação da Tri7 falhando cancela o lote e devolve lista
        # vazia. O ponteiro não pode andar -- senão a faixa é pulada.
        estado = {
            "id": 1, "proximo_inicial": 39856, "limite_inicial": 39855,
            "ultimo_conhecido": 39855, "proximo_revisao": 1,
        }
        cursor = MagicMock()
        cursor.fetchone.return_value = estado
        cursor.fetchall.return_value = []

        with patch.object(I, "conectar", return_value=_conexao(cursor)), \
                patch.object(I, "validar_configuracao_buscas"), \
                patch.object(I, "_consultar_lote",
                             return_value=([], "Autenticação na Tri7 falhou.")), \
                patch.object(I, "_estado_json", return_value={}), \
                patch.object(I, "registrar_auditoria_cursor"):
            resposta = I._executar_sincronizacao("NOVOS", 30, 0, MagicMock(), "TESTE")

        avancou = any(
            "SET ultimo_conhecido=GREATEST" in c.args[0]
            and "proximo_inicial" not in c.args[0]
            for c in cursor.execute.call_args_list
        )
        self.assertFalse(avancou, "ponteiro andou apesar de o lote ter falhado")
        # E a falha precisa chegar à interface, senão vira "nada novo".
        self.assertEqual(resposta["falha"], "Autenticação na Tri7 falhou.")
        self.assertEqual(resposta["encontradas"], 0)


if __name__ == "__main__":
    unittest.main()
