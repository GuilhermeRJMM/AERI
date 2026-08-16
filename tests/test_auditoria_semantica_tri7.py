import unittest
from unittest.mock import patch

from scripts.auditar_semantica_tri7 import (
    auditar_proprietarios,
    auditar_texto,
    filtrar_resultados_faixa,
    linha_ignorada_loteamento,
)


class TesteAuditoriaSemanticaTri7(unittest.TestCase):
    def test_alerta_nome_desconhecido_na_cadeia(self):
        texto = (
            "MATRÍCULA 1.253. PROPRIETÁRIOS: DESCONHECIDO. "
            "ORIGEM: registro anterior."
        )

        resultado = auditar_texto(1253, texto)

        self.assertIn("PROPRIETARIO_NOME_INVALIDO", resultado["alertas_cadeia"])

    def test_alerta_cosmetico_isolado_nao_escala_para_p0_critica(self):
        # PROPRIETARIO_NOME_INVALIDO é um alerta "crítico" que na prática
        # costuma ser uma heurística isolada (um nome mal extraído em uma
        # matrícula sem nenhum outro problema), não um sinal de dado
        # corrompido. Antes, qualquer ocorrência isolada dele bastava para
        # jogar a matrícula em P0-CRÍTICA junto de problemas realmente
        # graves (cadeia vazia, titularidade fora de 100% etc.), inflando
        # a fila de revisão prioritária com falsos positivos cosméticos.
        texto = (
            "MATRÍCULA 1.253. PROPRIETÁRIOS: DESCONHECIDO. "
            "ORIGEM: registro anterior."
        )

        resultado = auditar_texto(1253, texto)

        self.assertIn("PROPRIETARIO_NOME_INVALIDO", resultado["alertas_cadeia"])
        self.assertEqual(resultado["confianca_cadeia"], "MEDIA")
        self.assertEqual(resultado["prioridade_revisao"], "P1-CONFERIR")

    def test_alerta_grave_continua_escalando_para_p0_critica(self):
        texto = """
        MATRÍCULA 2. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        R.01-2 - COMPRA E VENDA. Texto sem qualificação de adquirente disponível.
        """

        resultado = auditar_texto(2, texto)

        self.assertIn("CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA", resultado["alertas"])
        self.assertEqual(resultado["confianca_cadeia"], "BAIXA")
        self.assertEqual(resultado["prioridade_revisao"], "P0-CRITICA")

    def test_proporcao_presumida_gera_alerta_sem_escalar_para_p0(self):
        # calcular_cadeia_dominial marca proporcao_incerta quando cai no
        # fallback de 100% sem nenhum sinal textual de fração/percentual.
        # A auditoria precisa expor isso como alerta (para revisão humana),
        # mas não deve tratá-lo como confirmação de erro -- é só uma
        # exposição de incerteza, então fica fora dos alertas críticos.
        texto = """
        MATRÍCULA 900. IMÓVEL: Lote 1.
        PROPRIETÁRIO: Pessoa Inicial, CPF 004.338.341-61.
        R.01-900 - COMPRA E VENDA. ADQUIRENTE: Pessoa Nova, CPF 111.222.333-44;
        sem outras qualificações.
        """

        resultado = auditar_texto(900, texto)

        self.assertIn("PROPORCAO_ADQUIRENTE_PRESUMIDA", resultado["alertas_cadeia"])
        self.assertEqual(resultado["confianca_cadeia"], "MEDIA")
        self.assertEqual(resultado["prioridade_revisao"], "P1-CONFERIR")

    def test_codigo_rural_de_ccir_nao_e_falso_alerta_de_incra(self):
        texto = """
        IMÓVEL: Fazenda Vera Cruz, com área de 2,4697ha.
        Certificado de Cadastro de Imóvel Rural - CCIR n.º 20891919192;
        código do imóvel rural: 999.962.897.760-7; área total: 2,0473ha.
        PROPRIETÁRIA: Empresa Rural Ltda., CNPJ 13.386.541/0001-41.
        """

        resultado = auditar_texto(32997, texto)

        self.assertNotIn("INCRA_NAO_EXTRAIDO", resultado["alertas"])

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

    def test_regularizacao_fundiaria_e_auditada_como_transferencia_integral(self):
        texto = """
        IMÓVEL: Lote 16 da Quadra 32, com área de 268,29m².
        PROPRIETÁRIO: Município de Morrinhos, CNPJ 01.789.551/0001-49.
        R.01-37.900 - REGULARIZAÇÃO FUNDIÁRIA. OUTORGANTE: Município de
        Morrinhos, CNPJ 01.789.551/0001-49. OUTORGADO: Joabes Marques Borges,
        CPF 644.931.051-00. IMÓVEL: O imóvel descrito na matrícula.
        LEGITIMAÇÃO FUNDIÁRIA: A aquisição da propriedade é originária, de
        forma plena, sem quaisquer cláusulas ou condições.
        """

        resultado = auditar_texto(37900, texto)

        self.assertEqual(resultado["atos_transferencia"], 1)
        self.assertEqual(resultado["titularidade_total"], 100.0)
        self.assertNotIn("ULTIMA_TRANSFERENCIA_INTEGRAL_DIVERGENTE", resultado["alertas"])

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

    def test_cancelamento_explicito_da_matricula_ja_e_reconhecido(self):
        texto = """
        MATRÍCULA 6. IMÓVEL: Fazenda Exemplo, com a área de 1,0000ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        AV.01-6 - CANCELAMENTO DE MATRÍCULA. Fica cancelada a matrícula acima.
        """

        resultado = auditar_texto(6, texto)

        self.assertEqual(resultado["situacao_aeri"], "ENCERRADA")
        self.assertNotIn("ENCERRAMENTO_NAO_RECONHECIDO", resultado["alertas_imovel"])

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

    def test_cancelamento_com_alvo_nao_conflita_com_outra_hipoteca_anterior(self):
        texto = """
        MATRÍCULA 12. IMÓVEL: Lote n.º 1, Quadra 2, com área de 300m².
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        R.01-12 - HIPOTECA. Primeira garantia.
        R.02-12 - HIPOTECA. Segunda garantia.
        AV.03-12 - CANCELAMENTO DE HIPOTECA. Fica cancelada a hipoteca do R.02.
        """
        retorno = {
            "resultado": "POSITIVA PARA ÔNUS",
            "proprietarios_atuais": [
                {"nome": "Pessoa Exemplo", "cpf": "004.338.341-61", "proporcao": "100%"}
            ],
            "atos": [
                {
                    "codigo": "R.01", "descricao": "R.01-12 - HIPOTECA.",
                    "categoria": "ÔNUS", "tipo_onus": "HIPOTECA", "status": "ATIVO",
                },
                {
                    "codigo": "R.02", "descricao": "R.02-12 - HIPOTECA.",
                    "categoria": "ÔNUS", "tipo_onus": "HIPOTECA", "status": "CANCELADO",
                },
                {
                    "codigo": "AV.03",
                    "descricao": "AV.03-12 - CANCELAMENTO DE HIPOTECA do R.02.",
                    "categoria": "CANCELAMENTO", "status": "ATIVO", "cancela_atos": ["R.02"],
                },
            ],
            "imovel": {
                "tipo": "URBANO",
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "identificacao": [
                    {"rotulo": "Matrícula", "valor": "12", "origem": "Consulta"},
                    {"rotulo": "Lote", "valor": "1", "origem": "Cabeçalho"},
                    {"rotulo": "Quadra", "valor": "2", "origem": "Cabeçalho"},
                ],
                "areas": [{"rotulo": "Área", "valor": "300 m²", "origem": "Cabeçalho"}],
                "cadastros": [],
            },
        }

        with patch("scripts.auditar_semantica_tri7.analisar_matricula", return_value=retorno):
            resultado = auditar_texto(12, texto)

        self.assertNotIn(
            "CANCELAMENTO_POSSIVELMENTE_INCOMPLETO",
            resultado["alertas_onus"],
        )

    def test_aditivo_de_re_ratificacao_nao_e_novo_onus(self):
        texto = """
        MATRÍCULA 13. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        R.01-13 - ADITIVO DE RE-RATIFICAÇÃO À CÉDULA RURAL HIPOTECÁRIA.
        Ficam ratificadas as demais condições da cédula original.
        """
        resultado = auditar_texto(13, texto)

        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", resultado["alertas_onus"])

    def test_vinculo_historico_por_cedula_e_classificado(self):
        texto = """
        MATRÍCULA 40. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        AV.01-40 - O imóvel acima está vinculado ao Banco do Brasil S/A,
        pela Cédula de 1º grau, emitida em 23/07/1975, vencível em 23/07/1976,
        inscrita sob o nº 3.507, fls. 192, Livro 9-E deste Cartório.
        """

        resultado = auditar_texto(40, texto)

        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", resultado["alertas_onus"])

    def test_renegociacao_nao_e_nova_constituicao_de_onus(self):
        texto = """
        MATRÍCULA 153. IMÓVEL: Fazenda. PROPRIETÁRIO: Pessoa Exemplo.
        AV.105-153 - RENEGOCIAÇÃO DA DÍVIDA E ALTERAÇÃO DO PRAZO DE VENCIMENTO.
        A dívida objeto do R.95 fica renegociada. O título anterior era uma
        confissão e assunção de dívida com garantia hipotecária.
        """
        resultado = auditar_texto(153, texto)
        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", resultado["alertas_onus"])

    def test_anuencia_e_alteracao_de_credor_nao_sao_novos_onus(self):
        texto = """
        MATRÍCULA 14. IMÓVEL: Fazenda Exemplo, com área de 10ha.
        PROPRIETÁRIO: Pessoa Exemplo, CPF 004.338.341-61.
        AV.01-14 - ANUÊNCIA. O credor hipotecário anui com a venda.
        AV.02-14 - ALTERAÇÃO DE CREDOR. Atualiza-se a denominação do credor.
        """
        resultado = auditar_texto(14, texto)

        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", resultado["alertas_onus"])


    def test_imovel_rural_com_lote_sem_quadra_nao_gera_alerta_urbano(self):
        texto = """
        MATRÍCULA 369. IMÓVEL: Lugar denominado Cordeiro, neste Município,
        constituído de terreno designado lote 3, com 8.160m², cadastrado no
        INCRA sob o nº 936.120.019.232. PROPRIETÁRIO: Pessoa Teste.
        """

        auditoria = auditar_texto(369, texto)

        self.assertNotIn("TIPO_IMOVEL_DIVERGENTE", auditoria["alertas"])
        self.assertNotIn("RUA_NAO_EXTRAIDO", auditoria["alertas"])

    def test_imovel_urbano_nao_exige_cadastros_rurais(self):
        texto = """
        MATRÍCULA 560. IMÓVEL: Rua 01, nesta Cidade, lote 07, quadra 13,
        com área de 240m². Cadastrado no INCRA sob o nº 13/07-SN.
        PROPRIETÁRIO: Pessoa Teste.
        """

        auditoria = auditar_texto(560, texto)

        self.assertNotIn("INCRA_NAO_EXTRAIDO", auditoria["alertas"])
        self.assertNotIn("DENOMINACAO_RURAL_NAO_EXTRAIDO", auditoria["alertas"])

    def test_ccir_totalmente_mascarado_nao_gera_pendencia_de_extracao(self):
        texto = """
        MATRÍCULA 10.684. IMÓVEL: Fazenda Buriti, com área de 10ha.
        PROPRIETÁRIO: Pessoa Teste.
        AV.01-10.684 - ATUALIZAÇÃO DO CCIR. Código do imóvel rural:
        xxx.xxx.xxx.xxx-x; área total: x,xxxxha. DOU FÉ.
        """

        auditoria = auditar_texto(10684, texto)

        self.assertNotIn("CCIR_NAO_EXTRAIDO", auditoria["alertas"])

    def test_area_totalizada_em_duas_glebas_nao_diverge(self):
        texto = """
        MATRÍCULA 148. IMÓVEL: Fazenda Almas. A) Gleba com 6 hectares e 50 ares
        e 127 hectares de campos, perfazendo o total de 133 hectares e 50 ares;
        B) outra gleba com 11 hectares e 17 hectares, totalizando: 28 hectares,
        13 ares e 21 centiares. PROPRIETÁRIO: Pessoa Teste.
        """

        auditoria = auditar_texto(148, texto)

        self.assertNotIn("AREA_REGISTRAL_DIVERGENTE", auditoria["alertas"])

    def test_area_total_nao_e_somada_novamente_com_quinhoes(self):
        texto = """
        MATRÍCULA 144. IMÓVEL: Fazenda Bom Jardim, com 206 hectares, 9 ares
        e 10 centiares de culturas e 524 hectares, 79 ares e 12 centiares de
        campos, totalizando: 730 hectares, 88 ares e 22 centiares, cabendo aos
        proprietários: Iolanda, totalizando 282,5511 hectares; Iara,
        totalizando 149,4437 hectares; e Décio, totalizando: 149 hectares,
        44 ares e 37 centiares. PROPRIETÁRIOS: Iolanda e outros.
        """

        auditoria = auditar_texto(144, texto)

        self.assertNotIn("AREA_REGISTRAL_DIVERGENTE", auditoria["alertas"])

    def test_penhor_rural_de_localizacao_e_confirmado_pela_auditoria(self):
        texto = """
        MATRÍCULA 17. IMÓVEL: Fazenda Exemplo. PROPRIETÁRIO: Pessoa Teste.
        AV.01-17 - PENHOR RURAL/IMÓVEL DE LOCALIZAÇÃO. Procede-se à averbação
        para constar a existência de bens apenhados localizados no imóvel,
        conforme penhor integrante de Cédula Rural Pignoratícia.
        """

        auditoria = auditar_texto(17, texto)

        self.assertNotIn(
            "ONUS_ATIVO_SEM_CONSTITUICAO_INDEPENDENTE",
            auditoria["alertas"],
        )

    def test_venda_com_alienacao_fiduciaria_e_confirmada_pela_auditoria(self):
        texto = """
        MATRÍCULA 244. IMÓVEL: Lote 1, Quadra 2. PROPRIETÁRIO: Pessoa Teste.
        R.06-244 - Escritura de Compra e Venda com financiamento e pacto adjeto
        de Alienação Fiduciária. O imóvel foi adquirido pelos compradores e
        dado em garantia fiduciária ao credor.
        """

        auditoria = auditar_texto(244, texto)

        self.assertNotIn(
            "ONUS_ATIVO_SEM_CONSTITUICAO_INDEPENDENTE",
            auditoria["alertas"],
        )

    def test_extincao_de_hipoteca_e_cancelamento(self):
        texto = """
        MATRÍCULA 1.407. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Teste.
        R.01-1.407 - HIPOTECA. O imóvel foi dado em hipoteca ao Banco.
        AV.03-1.407 - EXTINÇÃO DE HIPOTECA. Foi extinta a hipoteca do R.01.
        """

        auditoria = auditar_texto(1407, texto)

        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", auditoria["alertas"])

    def test_anuencia_conjugal_no_corpo_nao_esconde_hipoteca(self):
        texto = """
        MATRÍCULA 2.149. IMÓVEL: Fazenda Teste. PROPRIETÁRIO: Pessoa Teste.
        R.25-2.149 - HIPOTECA. PROPRIETÁRIO/HIPOTECANTE/DEVEDOR: Pessoa Teste,
        com anuência de seu cônjuge. CREDOR: Banco. O imóvel foi dado em hipoteca.
        """

        auditoria = auditar_texto(2149, texto)

        self.assertNotIn(
            "ONUS_ATIVO_SEM_CONSTITUICAO_INDEPENDENTE",
            auditoria["alertas"],
        )

    def test_adjudicacao_nao_e_novo_onus_por_citar_execucao_hipotecaria(self):
        texto = """
        MATRÍCULA 1.929. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Teste.
        R.02-1.929 - ADJUDICAÇÃO DE IMÓVEL. Carta extraída dos autos de execução
        hipotecária, adjudicado à credora hipotecária o imóvel desta matrícula.
        """

        auditoria = auditar_texto(1929, texto)

        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", auditoria["alertas"])

    def test_penhora_historica_com_procedo_ao_registro_e_confirmada(self):
        texto = """
        MATRÍCULA 2.776. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Teste.
        R.19-2.776 - Nos termos do mandado extraído da ação de execução,
        procedo ao registro da penhora sobre o imóvel desta matrícula.
        """

        auditoria = auditar_texto(2776, texto)

        self.assertNotIn(
            "ONUS_ATIVO_SEM_CONSTITUICAO_INDEPENDENTE", auditoria["alertas"]
        )

    def test_venda_e_alienacao_em_atos_seguidos_nao_divergem(self):
        texto = """
        MATRÍCULA 1.330. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Inicial.
        R.04-1.330 - Protocolo n.º 164.207. VENDA E COMPRA. TÍTULO: Instrumento
        Particular de Venda e Compra com Garantia de Alienação Fiduciária.
        ADQUIRENTE: Pessoa Compradora.
        R.05-1.330 - Protocolo n.º 164.207. ALIENAÇÃO FIDUCIÁRIA. DEVEDOR
        FIDUCIANTE: Pessoa Compradora. CREDOR FIDUCIÁRIO: Banco Exemplo.
        OBJETO DA GARANTIA: Em alienação fiduciária, o imóvel desta matrícula.
        """

        auditoria = auditar_texto(1330, texto)

        self.assertNotIn("ONUS_EXPLICITO_NAO_CLASSIFICADO", auditoria["alertas"])
        self.assertNotIn(
            "ONUS_ATIVO_SEM_CONSTITUICAO_INDEPENDENTE", auditoria["alertas"]
        )

    def test_leiloes_negativos_confirmam_cancelamento_da_alienacao(self):
        texto = """
        MATRÍCULA 3.538. IMÓVEL: Lote 1. PROPRIETÁRIO: Pessoa Devedora.
        R.07-3.538 - ALIENAÇÃO FIDUCIÁRIA. DEVEDOR FIDUCIANTE: Pessoa Devedora.
        CREDORA FIDUCIÁRIA: Caixa Exemplo. OBJETO DA GARANTIA: Em alienação
        fiduciária, o imóvel desta matrícula.
        AV.10-3.538 - LEILÕES NEGATIVOS / EXTINÇÃO DA DÍVIDA ORIGINÁRIA. Foram
        realizados dois leilões, sendo negativo o resultado de ambos, e a dívida
        originária da garantia da alienação fiduciária foi considerada extinta.
        """

        auditoria = auditar_texto(3538, texto)

        self.assertNotIn("CANCELAMENTO_DE_ONUS_SEM_ALVO", auditoria["alertas"])
        self.assertNotIn("CANCELAMENTO_POSSIVELMENTE_INCOMPLETO", auditoria["alertas"])


if __name__ == "__main__":
    unittest.main()
