import unittest
from types import SimpleNamespace

from backend.app.parser import separar_atos
from backend.app.proprietarios import calcular_cadeia_dominial


class TesteRegressoesMatriculas10151E17938(unittest.TestCase):
    def test_10151_aplica_aquisicao_historica_do_r1(self):
        texto = """
        MATRÍCULA 10.151. IMÓVEL: Fazenda Samambaia.
        PROPRIETÁRIOS: Valtuir Ipfarr da Silva e sua mulher Ivone de Matos
        Rodrigues da Silva, inscritos no CIC em conjunto sob o n.º
        305.923.488-49. TÍTULO AQUISITIVO: R-7-778.
        R-1-10.151. Nos termos da escritura pública, o imóvel objeto da
        presente matrícula foi adquirido por RENATO PEREIRA DA ROCHA,
        brasileiro, agricultor, inscrito no CIC n.º 216.181.278-53; por compra
        feita a Valtuir Ipfarr da Silva e sua mulher Ivone de Matos Rodrigues
        da Silva, inscritos no CIC em conjunto sob o n.º 305.923.488-49; pelo
        preço convencionado, sem condições. DOU FÉ.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            resultado,
            [{
                "nome": "RENATO PEREIRA DA ROCHA",
                "cpf": "216.181.278-53",
                "proporcao": "100%",
                "proporcao_incerta": False,
            }],
        )

    def test_17938_separa_companheira_expressamente_adquirente(self):
        texto = """
        MATRÍCULA 17.938. IMÓVEL: Lote urbano.
        PROPRIETÁRIO: Antônio Vendedor, CPF 864.556.138-72.
        R.06-17.938 - VENDA E COMPRA. TRANSMITENTE: Antônio Vendedor,
        CPF/MF 864.556.138-72. ADQUIRENTES: Cleusi Luiz de Castilho,
        brasileiro, solteiro, inscrito no CPF/MF sob o n.º 795.995.751-72,
        e sua companheira Adriana Aparecida da Silva, brasileira, solteira,
        inscrita no CPF sob o n.º 806.693.361-49, conviventes em união estável
        sob o regime da comunhão parcial de bens. IMÓVEL: A totalidade.
        """
        atos = [SimpleNamespace(descricao=item["texto"]) for item in separar_atos(texto)]

        resultado = calcular_cadeia_dominial(atos, texto)

        self.assertEqual(
            [(item["nome"], item["cpf"], item["proporcao"]) for item in resultado],
            [
                ("Cleusi Luiz de Castilho", "795.995.751-72", "50%"),
                ("Adriana Aparecida da Silva", "806.693.361-49", "50%"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
