import unittest

from scripts.auditar_semantica_tri7 import (
    auditar_proprietarios,
    auditar_texto,
    filtrar_resultados_faixa,
)


class TesteAuditoriaSemanticaTri7(unittest.TestCase):
    def test_resumo_considera_somente_a_faixa_solicitada(self):
        resultados = {
            1: {"status": "ERRO_API", "alertas": "AREA_NAO_EXTRAIDO"},
            13001: {"status": "OK", "alertas": ""},
            39767: {"status": "OK", "alertas": "TITULARIDADE_FORA_DE_100"},
            40000: {"status": "ERRO_API", "alertas": "CCI_NAO_EXTRAIDO"},
        }

        filtrados = filtrar_resultados_faixa(resultados, 13001, 39767)

        self.assertEqual(set(filtrados), {13001, 39767})

    def test_nao_alerta_quando_dados_e_encerramento_foram_extraidos(self):
        texto = """
        MATRÍCULA 1. IMÓVEL: Lote n.º 01, Quadra n.º 02, com área de 100,00m².
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61. ORIGEM: Matrícula anterior.
        AV.01-1 - DESIGNAÇÃO CADASTRAL DO IMÓVEL. O imóvel possui o seguinte código
        cadastral: CCI n.º 123.456xxx.xxxxxx.xxx. DOU FÉ.
        AV.02-1 - EDIFICAÇÃO. Foi edificada uma casa com 40,00m² de área construída.
        AV.03-1 - DESMEMBRAMENTO E MATRÍCULA. Averba-se o desmembramento do imóvel
        matriculado em duas glebas, sendo a primeira matriculada sob o n.º 10.001 e a
        segunda matriculada sob o n.º 10.002.
        """

        resultado = auditar_texto(1, texto)

        self.assertEqual(resultado["situacao_aeri"], "ENCERRADA")
        self.assertEqual(resultado["alertas"], "")
        self.assertTrue(resultado["extraiu_cci"])
        self.assertTrue(resultado["extraiu_area_construida"])

    def test_alerta_cadeia_vazia_quando_ha_transferencia(self):
        texto = """
        MATRÍCULA 2. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        R.01-2 - COMPRA E VENDA. Texto sem qualificação de adquirente disponível.
        """

        resultado = auditar_texto(2, texto)

        self.assertIn("CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA", resultado["alertas"])

    def test_nao_alerta_comprador_coberto_pelo_extrator(self):
        texto = """
        MATRÍCULA 3. IMÓVEL: Lote nº 1, Quadra 2, com área de 300m².
        PROPRIETÁRIO: Pessoa Inicial, CPF 004.338.341-61.
        R.01-3 - ARREMATAÇÃO. COMPRADOR: Pessoa Nova, CPF 111.222.333-44.
        IMÓVEL: A totalidade do imóvel.
        """

        resultado = auditar_texto(3, texto)

        self.assertNotIn("ADQUIRENTE_ROTULADO_NAO_EXTRAIDO", resultado["alertas"])

    def test_alerta_total_de_titularidade_inconsistente(self):
        resultado = auditar_proprietarios(
            "MATRÍCULA 4. IMÓVEL: Lote 1.",
            [{"nome": "Pessoa", "cpf": "004.338.341-61", "proporcao": "60%"}],
        )

        self.assertEqual(resultado["titularidade_total"], 60.0)


if __name__ == "__main__":
    unittest.main()
