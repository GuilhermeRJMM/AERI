from types import SimpleNamespace
import unittest

from backend.app.proprietarios import (
    calcular_cadeia_dominial,
    extrair_bloco,
    extrair_pessoas,
)


def ato(descricao):
    return SimpleNamespace(descricao=descricao)


class CorrecoesMatriculas47xxTest(unittest.TestCase):
    def test_remove_descricao_de_dominio_do_nome(self):
        pessoas = extrair_pessoas(
            "Do domínio útil sobre o terreno descrito e o prédio residencial "
            "nele edificado Feliciano Bernardo Ribeiro Filho, brasileiro, "
            "CPF n.º 016.583.791-87"
        )

        self.assertEqual(pessoas[0]["nome"], "Feliciano Bernardo Ribeiro Filho")

    def test_separa_coproprietario_com_titulo_profissional(self):
        descricao = (
            "COMPRA E VENDA. O imóvel foi adquirido por Dr. Jorge Alexandre "
            "Ribeiro, brasileiro, CIC n.º 020.887.111-04; e, Dr. João Alexandre "
            "Ribeiro, brasileiro, CIC n.º 012.920.051-49; por compra feita a "
            "Valdomiro Vieira."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Jorge Alexandre Ribeiro": "50%",
                "João Alexandre Ribeiro": "50%",
            },
        )

    def test_partilha_entre_com_percentuais_individuais(self):
        descricao = (
            "PARTILHA. O imóvel foi partilhado entre: 1)- Divina Carvalho da "
            "Silva, CPF n.º 463.771.581-49, na proporção de 70%; e, 2)- "
            "Welinton Marcos de Souza, CPF n.º 517.473.161-72, na proporção de "
            "30%. DOU FÉ."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            {item["nome"]: item["proporcao"] for item in resultado},
            {
                "Divina Carvalho da Silva": "70%",
                "Welinton Marcos de Souza": "30%",
            },
        )

    def test_menores_representados_sao_adquirentes_sem_cpf_do_pai(self):
        descricao = (
            "COMPRA E VENDA. O imóvel foi adquirido por Alvaro Faria do Vale "
            "Junior, Estela Rodrigues do Vale e Daisy Maria Rodrigues do Vale "
            "menores impúberes, estudantes, nesta ato representadas por seu pai "
            "Alvaro Faria do Vale, CIC n.º 311.773.876-20, por compra feita a "
            "Daniel Luiz de Rezende."
        )

        resultado = calcular_cadeia_dominial([ato(descricao)])

        self.assertEqual(
            [item["nome"] for item in resultado],
            [
                "Alvaro Faria do Vale Junior",
                "Estela Rodrigues do Vale",
                "Daisy Maria Rodrigues do Vale",
            ],
        )
        self.assertTrue(
            all(item["cpf"] == "CPF/CNPJ NÃO INFORMADO" for item in resultado)
        )

    def test_donataria_nao_e_tratada_como_doadora(self):
        descricao = (
            "DOAÇÃO. DOADORA: Elza Lunca Sussai, CPF n.º 628.839.841-15. "
            "DONATÁRIA: Alacir Sussai, CPF n.º 581.492.109-97. "
            "IMÓVEL: 75% do imóvel descrito na matrícula."
        )

        transmitentes = extrair_pessoas(extrair_bloco(descricao, "TRANSMITENTE"))

        self.assertEqual(
            transmitentes,
            [{"nome": "Elza Lunca Sussai", "cpf": "628.839.841-15"}],
        )


if __name__ == "__main__":
    unittest.main()
