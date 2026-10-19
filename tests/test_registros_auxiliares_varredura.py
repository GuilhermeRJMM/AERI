import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.app.rotas.registros_auxiliares import (
    _consultar_lote_tri7,
    _registrar_erro,
    _proximo_modo_automatico,
    _registrar_consulta_varredura,
    _selecionar_numeros_lacunas,
    _selecionar_numeros_novos,
)


class TesteVarreduraRegistrosAuxiliares(unittest.TestCase):
    def test_lote_preserva_respostas_concluidas_ao_ocorrer_falha_fatal(self):
        def consultar(numero, _cancelar):
            if numero == 29645:
                return {"numero": numero, "status": "FATAL", "erro": RuntimeError("credencial")}
            if numero == 29646:
                return {"numero": numero, "status": "CANCELADO"}
            return {"numero": numero, "status": "AUSENTE"}

        with patch("backend.app.rotas.registros_auxiliares._consultar_registro_auxiliar_tri7", side_effect=consultar):
            resultados, falha = _consultar_lote_tri7([29644, 29645, 29646])

        self.assertEqual([item["numero"] for item in resultados], [29644, 29645])
        self.assertEqual(resultados[1]["status"], "FATAL")
        self.assertEqual(falha, "credencial")

    def test_novos_revisita_ausencia_e_sonda_depois_do_ultimo_confirmado(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"numero": 29644}]
        cursor.fetchone.return_value = {"maior": 29656}

        numeros, reconsultadas, exploradas = _selecionar_numeros_novos(
            cursor, ultimo_confirmado=29656, tamanho=3,
        )

        self.assertEqual(numeros, [29644, 29657, 29658])
        self.assertEqual(reconsultadas, 1)
        self.assertEqual(exploradas, 2)
        self.assertIn("resultado='AUSENTE'", cursor.execute.call_args_list[0].args[0])

    def test_lacunas_faz_varredura_circular_sem_repetir_registro_indexado(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [{"numero": 29644}, {"numero": 29645}],
            [{"numero": 2}],
        ]

        numeros = _selecionar_numeros_lacunas(cursor, inicio=29644, limite=29667, tamanho=3)

        self.assertEqual(numeros, [29644, 29645, 2])
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertIn("generate_series", cursor.execute.call_args_list[0].args[0])
        self.assertIn("indice.numero IS NULL", cursor.execute.call_args_list[0].args[0])
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("OR varredura.resultado='AUSENTE'", sql)
        self.assertIn("varredura.resultado='ERRO'\n                   AND varredura.proxima_consulta_em<=NOW()", sql)

    def test_cada_ausencia_e_persistida_com_prazo_de_reconsulta(self):
        cursor = MagicMock()

        _registrar_consulta_varredura(cursor, 29644, "AUSENTE")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("registros_auxiliares_varredura_aeri", sql)
        self.assertIn("proxima_consulta_em", sql)
        self.assertEqual(parametros, (29644, "AUSENTE", 24))
        self.assertIn("tentativas=registros_auxiliares_varredura_aeri.tentativas + 1", sql)

    def test_sucesso_nao_marca_numero_de_sondagem_como_ausente(self):
        cursor = MagicMock()

        _registrar_consulta_varredura(cursor, 29644, "ENCONTRADO")

        sql, parametros = cursor.execute.call_args.args
        self.assertIn("resultado", sql)
        self.assertNotIn("AUSENTE", sql)
        self.assertEqual(parametros, (29644, "ENCONTRADO"))

    def test_falha_tem_prazo_de_retentativa_e_nao_some_da_fila(self):
        cursor = MagicMock()

        _registrar_erro(cursor, 29644, "LACUNAS", RuntimeError("falha de rede"))

        sql_falha, parametros_falha = cursor.execute.call_args_list[0].args
        sql_varredura, parametros_varredura = cursor.execute.call_args_list[1].args
        self.assertIn("proxima_tentativa_em", sql_falha)
        self.assertEqual(parametros_falha, (29644, "LACUNAS", "falha de rede"))
        self.assertIn("resultado='ERRO'", sql_varredura)
        self.assertEqual(parametros_varredura, (29644,))

    def test_modo_automatico_reserva_ciclo_para_lacunas(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "proximo_inicial": 29636,
            "limite_inicial": 29635,
            "ciclo_automatico": 2,
        }

        modo = _proximo_modo_automatico(cursor)

        self.assertEqual(modo, "LACUNAS")
        self.assertIn("ciclo_automatico=ciclo_automatico+1", cursor.execute.call_args.args[0])

    def test_carga_inicial_continua_ate_o_limite_declarado(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "proximo_inicial": 29636,
            "limite_inicial": 29667,
            "ciclo_automatico": 4,
        }

        self.assertEqual(_proximo_modo_automatico(cursor), "INICIAL")

    def test_migracao_nao_confunde_limite_com_registro_confirmado(self):
        raiz = Path(__file__).parents[1]
        sql = (raiz / "backend/app/migrations/053_varredura_lacunas_registros_auxiliares.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("registros_auxiliares_varredura_aeri", sql)
        self.assertIn("'AUSENTE'", sql)
        self.assertIn("SELECT MAX(numero) FROM registros_auxiliares_aeri", sql)
        self.assertNotIn("ultimo_existente = GREATEST(ultimo_existente, limite", sql)


if __name__ == "__main__":
    unittest.main()
