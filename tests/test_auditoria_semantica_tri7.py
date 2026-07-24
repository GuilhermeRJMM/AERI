import unittest
from unittest.mock import patch

from scripts.auditar_semantica_tri7 import (
    auditar_proprietarios,
    auditar_texto,
    filtrar_resultados_faixa,
    linha_ignorada_loteamento,
)


class TesteAuditoriaSemanticaTri7(unittest.TestCase):
    def test_loteamento_ignorado_nao_e_contabilizado_como_erro(self):
        resultado = linha_ignorada_loteamento(4964)

        self.assertEqual(resultado["status"], "IGNORADA_LOTEAMENTO")
        self.assertEqual(resultado["estado_auditoria"], "IGNORADA")
        self.assertEqual(resultado["veredito_onus"], "IGNORADO")
        self.assertFalse(resultado["alertas"])

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


    def test_detecta_encerramento_historico_com_em_consequencia(self):
        texto = """
        MATRÍCULA 5. IMÓVEL: Fazenda Exemplo, com a área de 6,0000ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        AV.01-5 - FUSÃO. Este imóvel foi matriculado sob o n.º 15.329,
        ficando em consequência encerrada esta matrícula.
        """

        resultado = auditar_texto(5, texto)

        self.assertNotIn("ENCERRAMENTO_NAO_RECONHECIDO", resultado["alertas_imovel"])

    def test_detecta_cancelamento_explicito_da_matricula(self):
        texto = """
        MATRÍCULA 6. IMÓVEL: Fazenda Exemplo, com a área de 1,0000ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        AV.01-6 - CANCELAMENTO DE MATRÍCULA. Fica cancelada a matrícula acima.
        """

        resultado = auditar_texto(6, texto)

        self.assertIn("ENCERRAMENTO_NAO_RECONHECIDO", resultado["alertas_imovel"])

    def test_detecta_area_cadastral_usada_como_area_registral(self):
        texto = """
        MATRÍCULA 7. IMÓVEL: Fazenda Exemplo, com a área de 10.000m².
        Cadastrado no INCRA com a área total de 178,2ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        """
        retorno = {
            "resultado": "NEGATIVA PARA ÔNUS",
            "atos": [],
            "proprietarios_atuais": [
                {"nome": "Pessoa Exemplo", "cpf": "004.338.341-61", "proporcao": "100%"}
            ],
            "imovel": {
                "tipo": "RURAL",
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "identificacao": [
                    {"rotulo": "Matrícula", "valor": "7", "origem": "Consulta"},
                    {"rotulo": "Denominação", "valor": "Fazenda Exemplo", "origem": "Cabeçalho"},
                ],
                "areas": [{"rotulo": "Área", "valor": "178,2 ha", "origem": "Cabeçalho"}],
                "cadastros": [],
            },
        }

        with patch("scripts.auditar_semantica_tri7.analisar_matricula", return_value=retorno):
            resultado = auditar_texto(7, texto)

        self.assertIn("AREA_REGISTRAL_DIVERGENTE", resultado["alertas_imovel"])

    def test_detecta_valores_extraidos_mas_sem_integridade(self):
        texto = """
        MATRÍCULA 8. IMÓVEL: Lote n.º 1, Quadra 2, com área de 300m²,
        situado na Rua Exemplo, Setor Centro.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        """
        retorno = {
            "resultado": "NEGATIVA PARA ÔNUS",
            "atos": [],
            "proprietarios_atuais": [{"nome": "A", "cpf": "", "proporcao": "100%"}],
            "imovel": {
                "tipo": "RURAL",
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "identificacao": [
                    {"rotulo": "Matrícula", "valor": "8", "origem": "Consulta"},
                    {"rotulo": "Lote", "valor": "1", "origem": "Cabeçalho"},
                    {"rotulo": "Quadra", "valor": "2", "origem": "Cabeçalho"},
                    {"rotulo": "Rua", "valor": "Rua Rua Exemplo", "origem": "Cabeçalho"},
                    {"rotulo": "Setor", "valor": 'Setor "Centro', "origem": "Cabeçalho"},
                ],
                "areas": [{"rotulo": "Área", "valor": "300 m²", "origem": "Cabeçalho"}],
                "cadastros": [
                    {
                        "rotulo": "Cadastro municipal",
                        "valor": "CCI 129674, 83.998 e 97",
                        "origem": "AV.01",
                    }
                ],
            },
        }

        with patch("scripts.auditar_semantica_tri7.analisar_matricula", return_value=retorno):
            resultado = auditar_texto(8, texto)

        self.assertIn("TIPO_IMOVEL_DIVERGENTE", resultado["alertas_imovel"])
        self.assertIn("RUA_COM_PREFIXO_DUPLICADO", resultado["alertas_imovel"])
        self.assertIn("SETOR_COM_QUALIFICADOR_RESIDUAL", resultado["alertas_imovel"])
        self.assertNotIn("CCI_COM_VALORES_CONTAMINADOS", resultado["alertas_imovel"])
        self.assertIn("PROPRIETARIO_NOME_INVALIDO", resultado["alertas_cadeia"])
        self.assertTrue(resultado["evidencias_imovel"])

    def test_dacao_integral_com_tomador_e_coberta_na_cadeia(self):
        texto = """
        MATRÍCULA 9. IMÓVEL: Lote n.º 1, Quadra 2, com área de 300m².
        PROPRIETÁRIA: Pessoa Antiga, CPF 004.338.341-61.
        R.01-9 - DAÇÃO EM PAGAMENTO. TRANSMITENTE/DADORA: Pessoa Antiga.
        ADQUIRENTE/TOMADOR: Empresa Nova Ltda., CNPJ 12.345.678/0001-90.
        IMÓVEL: O objeto desta matrícula.
        """

        resultado = auditar_texto(9, texto)

        self.assertNotIn("ULTIMA_TRANSFERENCIA_INTEGRAL_DIVERGENTE", resultado["alertas_cadeia"])

    def test_detecta_cancelamento_que_deixa_usufruto_duplicado_ativo(self):
        texto = """
        MATRÍCULA 10. IMÓVEL: Lote n.º 1, Quadra 2, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        R.01-10 - DOAÇÃO. Clausulado com reserva de usufruto vitalício.
        R.02-10 - USUFRUTO VITALÍCIO. Usufrutuária: Pessoa Doadora.
        AV.03-10 - CANCELAMENTO DE USUFRUTO. Fica cancelado o usufruto vitalício.
        """
        retorno = {
            "resultado": "POSITIVA PARA ÔNUS",
            "proprietarios_atuais": [
                {"nome": "Pessoa Exemplo", "cpf": "004.338.341-61", "proporcao": "100%"}
            ],
            "atos": [
                {
                    "codigo": "R.01",
                    "descricao": "R.01-10 - DOAÇÃO. Clausulado com reserva de usufruto vitalício.",
                    "categoria": "ÔNUS",
                    "tipo_onus": "USUFRUTO",
                    "status": "ATIVO",
                },
                {
                    "codigo": "R.02",
                    "descricao": "R.02-10 - USUFRUTO VITALÍCIO.",
                    "categoria": "ÔNUS",
                    "tipo_onus": "USUFRUTO",
                    "status": "CANCELADO",
                },
                {
                    "codigo": "AV.03",
                    "descricao": "AV.03-10 - CANCELAMENTO. Fica cancelado o usufruto vitalício.",
                    "categoria": "CANCELAMENTO",
                    "status": "ATIVO",
                    "cancela_atos": ["R.02"],
                },
            ],
            "imovel": {
                "tipo": "URBANO",
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "identificacao": [
                    {"rotulo": "Matrícula", "valor": "10", "origem": "Consulta"},
                    {"rotulo": "Lote", "valor": "1", "origem": "Cabeçalho"},
                    {"rotulo": "Quadra", "valor": "2", "origem": "Cabeçalho"},
                ],
                "areas": [{"rotulo": "Área", "valor": "300 m²", "origem": "Cabeçalho"}],
                "cadastros": [],
            },
        }

        with patch("scripts.auditar_semantica_tri7.analisar_matricula", return_value=retorno):
            resultado = auditar_texto(10, texto)

        self.assertIn("CANCELAMENTO_POSSIVELMENTE_INCOMPLETO", resultado["alertas_onus"])


    def test_setor_aeroporto_ii_nao_e_qualificador_residual(self):
        texto = """
        MATRÍCULA 10. IMÓVEL: Lote n.º 1, Quadra 2, do loteamento Setor Aeroporto II,
        com área de 300m². PROPRIETÁRIO: Pessoa Válida, CPF 004.338.341-61.
        """
        retorno = {
            "proprietarios_atuais": [
                {"nome": "Pessoa Válida", "cpf": "004.338.341-61", "proporcao": "100%"}
            ],
            "imovel": {
                "tipo": "URBANO",
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "identificacao": [
                    {"rotulo": "Matrícula", "valor": "10", "origem": "Consulta"},
                    {"rotulo": "Lote", "valor": "1", "origem": "Cabeçalho"},
                    {"rotulo": "Quadra", "valor": "2", "origem": "Cabeçalho"},
                    {"rotulo": "Setor", "valor": "Setor Aeroporto II", "origem": "Cabeçalho"},
                ],
                "areas": [{"rotulo": "Área", "valor": "300 m²", "origem": "Cabeçalho"}],
                "cadastros": [],
            },
        }

        with patch("scripts.auditar_semantica_tri7.analisar_matricula", return_value=retorno):
            resultado = auditar_texto(10, texto)

        self.assertNotIn("SETOR_COM_QUALIFICADOR_RESIDUAL", resultado["alertas_imovel"])

    def test_cancelamento_antigo_nao_conflita_com_onus_posterior(self):
        texto = """
        MATRÍCULA 11. IMÓVEL: Lote n.º 1, Quadra 2, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        R.01-11 - ALIENAÇÃO FIDUCIÁRIA.
        AV.02-11 - CANCELAMENTO DE ALIENAÇÃO FIDUCIÁRIA. Fica cancelada a
        alienação fiduciária constante do R.01.
        R.03-11 - ALIENAÇÃO FIDUCIÁRIA. Nova garantia constituída posteriormente.
        """
        retorno = {
            "resultado": "POSITIVA PARA ÔNUS",
            "proprietarios_atuais": [
                {"nome": "Pessoa Exemplo", "cpf": "004.338.341-61", "proporcao": "100%"}
            ],
            "atos": [
                {
                    "codigo": "R.01",
                    "descricao": "R.01-11 - ALIENAÇÃO FIDUCIÁRIA.",
                    "categoria": "ÔNUS",
                    "tipo_onus": "ALIENAÇÃO FIDUCIÁRIA",
                    "status": "CANCELADO",
                },
                {
                    "codigo": "AV.02",
                    "descricao": "AV.02-11 - CANCELAMENTO DE ALIENAÇÃO FIDUCIÁRIA.",
                    "categoria": "CANCELAMENTO",
                    "status": "ATIVO",
                    "cancela_atos": ["R.01"],
                },
                {
                    "codigo": "R.03",
                    "descricao": "R.03-11 - ALIENAÇÃO FIDUCIÁRIA.",
                    "categoria": "ÔNUS",
                    "tipo_onus": "ALIENAÇÃO FIDUCIÁRIA",
                    "status": "ATIVO",
                },
            ],
            "imovel": {
                "tipo": "URBANO",
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "identificacao": [
                    {"rotulo": "Matrícula", "valor": "11", "origem": "Consulta"},
                    {"rotulo": "Lote", "valor": "1", "origem": "Cabeçalho"},
                    {"rotulo": "Quadra", "valor": "2", "origem": "Cabeçalho"},
                ],
                "areas": [{"rotulo": "Área", "valor": "300 m²", "origem": "Cabeçalho"}],
                "cadastros": [],
            },
        }

        with patch("scripts.auditar_semantica_tri7.analisar_matricula", return_value=retorno):
            resultado = auditar_texto(11, texto)

        self.assertNotIn(
            "CANCELAMENTO_POSSIVELMENTE_INCOMPLETO",
            resultado["alertas_onus"],
        )


if __name__ == "__main__":
    unittest.main()
