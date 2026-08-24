import unittest
from unittest.mock import MagicMock, Mock, patch

from backend.app.rotas.livro_protocolos import _reindexar_registros_alterados
from backend.app.servicos.livro_protocolos import (
    referencias_textos_protocolo,
    registros_alterados_no_protocolo,
)


def _item(tipo, numero, com_ato=True):
    item = {"dados_imovel": {"tipo_registro": tipo, "numero_registro": numero}}
    if com_ato:
        item["atos_registrados"] = {"ato_tipo": "R", "ato_numero": 5}
    return item


def _conexao_falsa():
    conexao = MagicMock()
    cursor = MagicMock()
    conexao.__enter__.return_value = conexao
    conexao.cursor.return_value.__enter__.return_value = cursor
    return conexao


class TesteRegistrosAlterados(unittest.TestCase):
    def test_inclui_registro_auxiliar_alem_da_matricula(self):
        # referencias_textos_protocolo existe para a conferência e só precisa
        # do texto das matrículas. Para saber o que ficou desatualizado no
        # índice, os Registros Auxiliares também contam.
        protocolo = {"itens_do_pedido": [_item("M", 24070), _item("RA", 29555)]}

        self.assertEqual(referencias_textos_protocolo(protocolo), {("M", 24070)})
        self.assertEqual(
            registros_alterados_no_protocolo(protocolo),
            {("M", 24070), ("RA", 29555)},
        )

    def test_ignora_item_sem_ato_registrado_ou_sem_numero(self):
        protocolo = {"itens_do_pedido": [
            _item("M", 24070, com_ato=False),   # prenotado, ainda não registrou
            _item("RA", 0),                     # número inválido
            _item("M", 30181),                  # este conta
        ]}

        self.assertEqual(registros_alterados_no_protocolo(protocolo), {("M", 30181)})


class TesteReindexacaoPeloLivro(unittest.TestCase):
    def setUp(self):
        self.cliente = Mock()

    def _reindexar(self, alterados, cache):
        with patch("backend.app.rotas.livro_protocolos.conectar", return_value=_conexao_falsa()), \
                patch("backend.app.rotas.livro_protocolos.registrar_auditoria_cursor"), \
                patch("backend.app.rotas.livro_protocolos._salvar_indice_matricula",
                      return_value=({}, False, True, {}, False)) as salvar_m, \
                patch("backend.app.rotas.livro_protocolos._salvar_indice_auxiliar",
                      return_value=({}, True)) as salvar_ra:
            relatorio = _reindexar_registros_alterados(
                alterados, cache, self.cliente, Mock(), "TESTE",
            )
        return relatorio, salvar_m, salvar_ra

    def test_matricula_reaproveita_o_texto_ja_baixado_na_conferencia(self):
        # O ganho central: a conferência já baixou o texto da matrícula, então
        # reindexar não custa consulta nova à Tri7.
        cache = {("M", 24070): ("MATRÍCULA 24.070 ...", None)}

        relatorio, salvar_m, _ = self._reindexar({("M", 24070)}, cache)

        self.cliente.buscar_texto_matricula.assert_not_called()
        salvar_m.assert_called_once()
        self.assertEqual(relatorio["matriculas"], 1)
        self.assertEqual(relatorio["matriculasAlteradas"], 1)
        self.assertEqual(relatorio["falhas"], 0)

    def test_matricula_fora_do_cache_e_consultada(self):
        self.cliente.buscar_texto_matricula.return_value = {"texto": "MATRÍCULA 1 ..."}

        relatorio, salvar_m, _ = self._reindexar({("M", 1)}, {})

        self.cliente.buscar_texto_matricula.assert_called_once_with(1)
        salvar_m.assert_called_once()
        self.assertEqual(relatorio["matriculas"], 1)

    def test_registro_auxiliar_consulta_o_proprio_texto(self):
        self.cliente.buscar_texto_registro_auxiliar.return_value = {"texto": "CPR ..."}

        relatorio, _, salvar_ra = self._reindexar({("RA", 29555)}, {})

        self.cliente.buscar_texto_registro_auxiliar.assert_called_once_with(29555)
        salvar_ra.assert_called_once()
        self.assertEqual(relatorio["registrosAuxiliares"], 1)
        self.assertEqual(relatorio["registrosAuxiliaresNovos"], 1)

    def test_falha_em_um_numero_nao_derruba_os_demais(self):
        # A conferência do dia não pode ser perdida porque um número falhou.
        self.cliente.buscar_texto_registro_auxiliar.side_effect = RuntimeError("Tri7 fora")
        cache = {("M", 24070): ("MATRÍCULA 24.070 ...", None)}

        relatorio, salvar_m, _ = self._reindexar({("M", 24070), ("RA", 29555)}, cache)

        salvar_m.assert_called_once()
        self.assertEqual(relatorio["matriculas"], 1)
        self.assertEqual(relatorio["falhas"], 1)
        self.assertEqual(relatorio["numerosComFalha"], ["RA.29555"])

    def test_sem_alteracoes_nao_abre_conexao(self):
        with patch("backend.app.rotas.livro_protocolos.conectar") as conectar_mock:
            relatorio = _reindexar_registros_alterados(
                set(), {}, self.cliente, Mock(), "TESTE",
            )

        conectar_mock.assert_not_called()
        self.assertEqual(relatorio["matriculas"], 0)


if __name__ == "__main__":
    unittest.main()
