import json
import unittest
from pathlib import Path

from scripts.exportar_inventario_registral import (
    NAO_CONSTA,
    _possivel_registro_loteamento,
    aplicar_triagem_loteamentos,
    achatar_atos,
    achatar_proprietarios,
    achatar_resultado,
    compactar_checkpoint,
    corrigir_situacoes_sinalizadas,
)


class TesteExportarInventarioRegistral(unittest.TestCase):
    def test_campos_ausentes_sao_exibidos_como_nao_consta(self):
        resultado = {
            "resultado": "NEGATIVA PARA ÔNUS",
            "publicidade": "SEM PUBLICIDADE",
            "atos": [],
            "proprietarios_atuais": [],
            "imovel": {
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "tipo": "URBANO",
                "identificacao": [{"rotulo": "Matrícula", "valor": "10", "origem": "Consulta Tri7"}],
                "confrontacoes": [],
                "areas": [],
                "cadastros": [],
                "restricoes": [],
                "divergencias": [],
                "alertas": [],
            },
        }
        auditoria = {
            "veredito_onus": "OK",
            "veredito_cadeia": "OK",
            "veredito_imovel": "OK",
            "confianca_onus": "ALTA",
            "confianca_cadeia": "ALTA",
            "confianca_imovel": "ALTA",
            "prioridade_revisao": "P2-VALIDADA",
            "estado_auditoria": "VALIDADA_AUTOMATICAMENTE",
        }

        linha = achatar_resultado(10, "MATRÍCULA 10. IMÓVEL: Lote urbano.", resultado, auditoria, 5)

        self.assertEqual(linha["cep"], NAO_CONSTA)
        self.assertEqual(linha["cci"], NAO_CONSTA)
        self.assertEqual(linha["area_registral"], NAO_CONSTA)
        self.assertEqual(linha["nome_imovel_rural"], NAO_CONSTA)

    def test_preserva_cci_cep_e_origens(self):
        resultado = {
            "resultado": "NEGATIVA PARA ÔNUS",
            "publicidade": "SEM PUBLICIDADE",
            "atos": [],
            "proprietarios_atuais": [],
            "imovel": {
                "situacao": {"status": "ATIVA", "origem": "Matrícula"},
                "tipo": "URBANO",
                "identificacao": [],
                "confrontacoes": [],
                "areas": [],
                "cadastros": [
                    {"rotulo": "Cadastro municipal", "valor": "CCI 139.796", "origem": "AV.02"},
                    {"rotulo": "CEP", "valor": "75.656-118", "origem": "AV.01"},
                ],
                "restricoes": [],
                "divergencias": [],
                "alertas": [],
            },
        }
        linha = achatar_resultado(39000, "MATRÍCULA 39.000.", resultado, {}, 5)

        self.assertEqual(linha["cci"], "CCI 139.796")
        self.assertEqual(linha["cci_origem"], "AV.02")
        self.assertEqual(linha["cep"], "75.656-118")
        self.assertEqual(linha["cep_origem"], "AV.01")

    def test_matricula_sem_proprietario_ou_ato_recebe_linha_explicita(self):
        proprietarios = achatar_proprietarios(1, "SEM_TEXTO", [])
        atos = achatar_atos(1, "SEM_TEXTO", [])

        self.assertEqual(proprietarios[0]["nome"], NAO_CONSTA)
        self.assertEqual(atos[0]["codigo_ato"], NAO_CONSTA)

    def test_identifica_plano_de_loteamento_sem_confundir_confrontacoes(self):
        loteamento = """
        MATRÍCULA 4.964. IMÓVEL: Lugar denominado Cordeiro, com 39 hectares,
        confrontando com o loteamento Vila São José. PROPRIETÁRIO: Pessoa Exemplo.
        R.01-4.964. Plano de Loteamento: Características: Área dos Lotes 241.644m².
        Número de Lotes: 562. Número de Quadras: 35.
        Tipo de Loteamento Segundo seu Uso: Residencial e Comercial.
        LOTEAMENTO SETOR CRISTO REDENTOR
        Quadra n.º 01, com 23 Lotes.
        """
        lote_comum = """
        MATRÍCULA 10. IMÓVEL: Lote 1, confrontando com o loteamento Vila São José.
        PROPRIETÁRIO: Pessoa Exemplo.
        """

        self.assertEqual(_possivel_registro_loteamento(loteamento), "SIM")
        self.assertEqual(_possivel_registro_loteamento(lote_comum), "NÃO")

    def test_corrige_situacao_sinalizada_e_recalcula_auditoria(self):
        resultados = {
            64: {
                "numero_matricula": 64,
                "status_processamento": "OK",
                "matricula": {
                    "situacao_imovel": "ATIVA",
                    "situacao_origem": "Matrícula",
                    "alertas_auditoria_onus": NAO_CONSTA,
                    "alertas_auditoria_cadeia": NAO_CONSTA,
                    "alertas_auditoria_imovel": "ENCERRAMENTO_NAO_RECONHECIDO",
                    "confianca_onus": "ALTA",
                    "confianca_cadeia_dominial": "ALTA",
                    "confianca_dados_imovel": "BAIXA",
                },
            }
        }

        self.assertEqual(corrigir_situacoes_sinalizadas(resultados), 1)
        matricula = resultados[64]["matricula"]
        self.assertEqual(matricula["situacao_imovel"], "ENCERRADA")
        self.assertEqual(matricula["alertas_auditoria_imovel"], NAO_CONSTA)
        self.assertEqual(matricula["veredito_dados_imovel"], "OK")
        self.assertEqual(matricula["prioridade_revisao"], "P2-VALIDADA")

    def test_compacta_checkpoint_em_ordem_sem_duplicatas(self):
        resultados = {
            2: {"numero_matricula": 2},
            1: {"numero_matricula": 1},
        }
        caminho = Path.cwd() / "output" / "relatorios" / ".checkpoint-teste.jsonl"
        try:
            compactar_checkpoint(caminho, resultados)
            linhas = [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines()]
        finally:
            caminho.unlink(missing_ok=True)

        self.assertEqual([linha["numero_matricula"] for linha in linhas], [1, 2])

    def test_triagem_de_loteamento_separa_matricula_mae_de_lote_derivado(self):
        resultados = {
            4964: {
                "status_processamento": "OK",
                "matricula": {"lote": NAO_CONSTA, "possivel_registro_loteamento": "NÃO"},
            },
            20804: {
                "status_processamento": "OK",
                "matricula": {"lote": NAO_CONSTA, "possivel_registro_loteamento": "NÃO"},
            },
            21065: {
                "status_processamento": "OK",
                "matricula": {"lote": "1", "possivel_registro_loteamento": "NÃO"},
            },
        }
        caminho = Path.cwd() / "output" / "relatorios" / ".loteamentos-teste.csv"
        try:
            caminho.write_text(
                "numero_matricula,status,registro_loteamento\n"
                "4964,OK,SIM\n20804,OK,SIM\n21065,OK,SIM\n",
                encoding="utf-8",
            )
            aplicar_triagem_loteamentos(resultados, caminho)
        finally:
            caminho.unlink(missing_ok=True)

        self.assertEqual(resultados[4964]["matricula"]["possivel_registro_loteamento"], "SIM")
        self.assertEqual(resultados[20804]["matricula"]["possivel_registro_loteamento"], "REVISAR")
        self.assertEqual(resultados[21065]["matricula"]["possivel_registro_loteamento"], "NÃO")


if __name__ == "__main__":
    unittest.main()
