"""Cobertura dos caminhos do Registro Auxiliar que rodavam sem teste.

O módulo é usado todos os dias no balcão e tinha a pior relação
teste/linha do projeto -- os dois defeitos encontrados em 17/08 (dígito
solto virando filtro de documento e segundo devedor ligado por "; e 2)-")
viveram nele por isso.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from backend.app.rotas.registros_auxiliares import (
    _estado_json,
    _proximo_modo_automatico,
    pesquisar_registros_auxiliares,
)
from backend.app.servicos.registros_auxiliares import (
    _formatar_documento,
    extrair_indice_registro_auxiliar,
    normalizar_busca,
    normalizar_safra,
    registro_auxiliar_json,
    resumo_certidao_registro_auxiliar,
)

os.environ.setdefault("AERI_BUSCAS_HMAC_KEY", "segredo-registros-auxiliares-teste")


def _cursor(fetchone=None, fetchall=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone or {}
    cursor.fetchall.return_value = fetchall or []
    return cursor


class TesteFormatacaoDeDocumento(unittest.TestCase):
    def test_cpf_e_cnpj_saem_mascarados_no_padrao_brasileiro(self):
        self.assertEqual(_formatar_documento("12345678901"), "123.456.789-01")
        self.assertEqual(_formatar_documento("12345678000190"), "12.345.678/0001-90")

    def test_documento_de_tamanho_atipico_e_devolvido_como_veio(self):
        # Registro antigo pode trazer CIC de 9 dígitos; inventar máscara
        # seria pior que preservar o que está escrito.
        self.assertEqual(_formatar_documento("123456789"), "123456789")


class TesteNormalizacoes(unittest.TestCase):
    def test_safra_com_dois_digitos_e_expandida(self):
        self.assertEqual(normalizar_safra("26/27"), "2026/2027")
        self.assertEqual(normalizar_safra("2026/2027"), "2026/2027")

    def test_safra_de_ano_unico_fica_como_veio(self):
        # Um ano só não vira intervalo: a busca casa pelo que está indexado.
        self.assertEqual(normalizar_safra("2026"), "2026")

    def test_texto_sem_ano_atravessa_sem_alteracao(self):
        # Não há intervalo a deduzir; devolver como veio deixa a pesquisa
        # simplesmente não encontrar, em vez de inventar uma safra.
        self.assertEqual(normalizar_safra("safra da seca"), "safra da seca")

    def test_busca_ignora_acento_e_caixa(self):
        self.assertEqual(normalizar_busca("José Antônio"), "JOSE ANTONIO")


class TesteSituacaoDoRegistro(unittest.TestCase):
    def test_baixa_parcial_nao_baixa_o_registro(self):
        # Liberar parte da garantia não extingue o registro: só o
        # cancelamento integral muda a situação.
        texto = """
        R.01-29.600 - PENHOR AGRÍCOLA. EMITENTE/DEVEDOR: João da Silva,
        CPF 123.456.789-01. Identificação do Produto: Soja; Safra: 2026/2027.
        AV.02-29.600 - Fica liberada parcialmente a garantia, permanecendo o
        restante do penhor em vigor.
        """

        self.assertEqual(extrair_indice_registro_auxiliar(29600, texto)["situacao"], "ATIVO")

    def test_cancelamento_integral_baixa(self):
        texto = """
        R.01-29.601 - PENHOR AGRÍCOLA. EMITENTE/DEVEDOR: João da Silva,
        CPF 123.456.789-01. Identificação do Produto: Soja; Safra: 2026/2027.
        AV.02-29.601 - CANCELAMENTO TOTAL DO PENHOR constante do R.01.
        """

        self.assertEqual(extrair_indice_registro_auxiliar(29601, texto)["situacao"], "BAIXADO")


class TesteJsonDoRegistro(unittest.TestCase):
    def test_json_expoe_o_indice_sem_o_texto_integral(self):
        # O índice existe justamente para não guardar texto registral.
        from datetime import datetime, timezone

        item = {
            "numero": 29555, "modalidade": "ALIENAÇÃO", "situacao": "ATIVO",
            "pessoas": [{"nome": "Nilo", "documento": "499.654.171-72", "papel": "EMITENTE"}],
            "produtos": ["SOJA"], "safras": ["2026/2027"],
            "texto_hash": "a" * 64, "nomes_busca": "NILO",
            "documentos_busca": "49965417172",
            "consultado_em": datetime(2026, 8, 17, tzinfo=timezone.utc),
        }

        saida = registro_auxiliar_json(item)

        self.assertEqual(saida["numero"], 29555)
        self.assertEqual(saida["situacao"], "ATIVO")
        for vazado in ("texto", "texto_hash", "nomes_busca", "documentos_busca"):
            self.assertNotIn(vazado, saida)
        self.assertNotIn("49965417172", str(saida))


class TesteResumoDaCertidao(unittest.TestCase):
    def test_com_registros_a_certidao_e_positiva_e_cobra_por_registro(self):
        um = resumo_certidao_registro_auxiliar(1)
        tres = resumo_certidao_registro_auxiliar(3)

        self.assertEqual(um["resultado"], "POSITIVA")
        self.assertEqual(tres["quantidadeRegistros"], 3)
        self.assertGreater(float(tres["valorCertidao"]), float(um["valorCertidao"]))

    def test_sem_registros_a_certidao_e_negativa_mas_ainda_e_cobrada(self):
        # Certidão negativa também tem emolumento: o multiplicador é 1.
        resumo = resumo_certidao_registro_auxiliar(0)

        self.assertEqual(resumo["resultado"], "NEGATIVA")
        self.assertEqual(resumo["quantidadeRegistros"], 0)
        self.assertGreater(float(resumo["valorCertidao"]), 0)


class TesteFiltrosDaPesquisa(unittest.TestCase):
    def _executar(self, **kwargs):
        conexao = MagicMock()
        cursor = _cursor()
        conexao.__enter__.return_value = conexao
        conexao.cursor.return_value.__enter__.return_value = cursor
        with patch("backend.app.rotas.registros_auxiliares.conectar", return_value=conexao):
            pesquisar_registros_auxiliares(_usuario="TESTE", **kwargs)
        chamada = cursor.execute.call_args
        return chamada.args[0], chamada.args[1]

    def test_modalidade_alienacao_vai_acentuada_para_o_banco(self):
        # A interface manda ALIENACAO sem acento; a coluna guarda com.
        sql, parametros = self._executar(
            busca="João da Silva", produto="Soja", safra="2026/2027",
            modalidade="ALIENACAO",
        )

        self.assertIn("modalidade=%s", sql)
        self.assertIn("ALIENAÇÃO", parametros)

    def test_pesquisa_exige_produto_e_safra(self):
        from fastapi import HTTPException

        for faltando in ({"produto": ""}, {"safra": ""}):
            with self.subTest(faltando=faltando):
                with self.assertRaises(HTTPException) as erro:
                    self._executar(
                        busca="João da Silva",
                        **{"produto": "Soja", "safra": "2026/2027", **faltando},
                    )
                self.assertEqual(erro.exception.status_code, 422)

    def test_modalidade_invalida_e_recusada(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as erro:
            self._executar(
                busca="João", produto="Soja", safra="2026/2027",
                modalidade="QUALQUER",
            )
        self.assertEqual(erro.exception.status_code, 422)

    def test_somente_registros_ativos_entram_na_pesquisa(self):
        sql, _ = self._executar(busca="João da Silva", produto="Soja", safra="2026/2027")

        self.assertIn("situacao='ATIVO'", sql)


class TesteModoAutomaticoDoCron(unittest.TestCase):
    def test_carga_inicial_tem_prioridade(self):
        cursor = _cursor(fetchone={
            "proximo_inicial": 500, "limite_inicial": 29538,
            "ultimo_conhecido": 29538, "proximo_revisao": 1,
        })

        self.assertEqual(_proximo_modo_automatico(cursor), "INICIAL")

    def test_erro_pendente_tem_prioridade_sobre_buscar_novos(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"proximo_inicial": 29539, "limite_inicial": 29538,
             "ultimo_conhecido": 29538, "proximo_revisao": 1},
            {"total": 4},
        ]

        self.assertEqual(_proximo_modo_automatico(cursor), "ERROS")

    def test_sem_erro_pendente_passa_a_buscar_novos(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [
            {"proximo_inicial": 29539, "limite_inicial": 29538,
             "ultimo_conhecido": 29538, "proximo_revisao": 1},
            {"total": 0},
        ]

        self.assertEqual(_proximo_modo_automatico(cursor), "NOVOS")


if __name__ == "__main__":
    unittest.main()
