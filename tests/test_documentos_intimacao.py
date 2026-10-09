from datetime import date
from unittest.mock import patch

from backend.app.servicos.documentos_intimacao import (
    ErroDocumentoIntimacao,
    analisar_pdfs_intimacao,
    complementar_matricula,
    extrair_dados_documento_rtd,
    estruturar_endereco,
)


OFICIO = """
Ofício nº 217507 / 2026 CESAV/BU
1. CAIXA ECONÔMICA FEDERAL - CNPJ 00.360.305/0001-04, credor(a) fiduciário(a)
Fiduciante(s): ROGERIO CARLOS MACHADO - CPF:94439095100, Solteiro
Matrícula(s): 30338
Endereço: Rua onze, nº51, Quadra 07 Lote 14b, Jardim America, MORRINHOS/GO, CEP 75650000
Contrato: 844441753253, firmado em:18/01/2018
"""

PROJECAO = """
Contrato de financiamento imobiliário Matrícula do Imóvel
844441753253 30338
Devedores:
ROGERIO CARLOS MACHADO - CPF:94439095100
Endereço do imóvel:
Rua, onze, 51, Quadra 07 Lote 14b, Jardim America, MORRINHOS-GO, cep:75650000
Endereço de Intimação:
Rua, onze, 51, Quadra 07 Lote 14b, Jardim America, MORRINHOS-GO, cep:75650000
Relação de projeção:
Data Recebimento Valor Purga do Débito
08/10/2026 2.879,26 09/10/2026 2.879,34
"""


def test_extrai_dados_de_requerimento_e_projecao_sem_gravar_conteudo():
    with patch(
        "backend.app.servicos.documentos_intimacao._ler_pdf",
        side_effect=[OFICIO, PROJECAO],
    ):
        resultado = analisar_pdfs_intimacao(
            b"%PDF oficio", b"%PDF projecao", date(2026, 10, 9), "IN01688738C", "186462"
        )

    assert resultado["processoCredor"] == "217507/2026"
    assert resultado["credor"] == {"nome": "CAIXA ECONÔMICA FEDERAL", "cnpj": "00360305000104"}
    assert resultado["devedores"] == [{"nome": "ROGERIO CARLOS MACHADO", "cpf": "94439095100"}]
    assert resultado["matricula"] == "30338"
    assert resultado["contrato"] == {"numero": "844441753253", "data": "18/01/2018"}
    assert resultado["projecao"]["valor"] == "2879.34"
    assert resultado["projecao"]["extenso"] == "dois mil oitocentos e setenta e nove reais e trinta e quatro centavos"
    assert resultado["projecao"]["exatoNaDataDeHoje"] is True
    assert len(resultado["enderecos"]) == 1


def test_nao_escolhe_valor_futuro_se_nao_houver_linha_para_hoje():
    with patch(
        "backend.app.servicos.documentos_intimacao._ler_pdf",
        side_effect=[OFICIO, PROJECAO],
    ):
        resultado = analisar_pdfs_intimacao(
            b"%PDF oficio", b"%PDF projecao", date(2026, 10, 11), "IN01688738C"
        )

    assert resultado["projecao"]["valor"] == ""
    assert resultado["projecao"]["exatoNaDataDeHoje"] is False
    assert any("não contém valor para a data de hoje" in aviso for aviso in resultado["avisos"])


def test_valores_divergentes_no_mesmo_dia_nao_geram_texto_com_valor_arbitrario():
    projecao = PROJECAO + "\n09/10/2026 3.000,00\n"
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", side_effect=[OFICIO, projecao]):
        resultado = analisar_pdfs_intimacao(
            b"%PDF oficio", b"%PDF projecao", date(2026, 10, 9), "IN01688738C"
        )
    assert resultado["projecao"]["valor"] == ""
    assert resultado["projecao"]["divergenciaNaData"] is True
    assert any("valores diferentes" in aviso for aviso in resultado["avisos"])


def test_endereco_fica_sinalizado_para_conferencia_humana():
    endereco = estruturar_endereco(
        "Rua, onze, 51, Quadra 07 Lote 14b, Jardim America, MORRINHOS-GO, cep:75650000"
    )
    assert endereco["logradouro"] == "Rua onze"
    assert endereco["numero"] == "51"
    assert endereco["complemento"] == "Quadra 07 Lote 14b"
    assert endereco["bairro"] == "Jardim America"
    assert endereco["cidade"].upper() == "MORRINHOS"
    assert endereco["uf"] == "GO"
    assert endereco["cep"] == "75650000"
    assert endereco["revisaoObrigatoria"] is True


def test_matricula_com_digito_verificador_identifica_registro_sem_escolher_outro():
    dados = {"contrato": {"numero": "844441753253"}, "avisos": []}
    complementar_matricula(dados, """R.03-30.338 - ALIENAÇÃO FIDUCIÁRIA. Contrato de Compra e Venda de Imóvel,
        Mútuo e Alienação Fiduciária em Garantia n.º 8.4444.1753253-0, datado de 18.01.2018.
        R.09-30.338 - VENDA E COMPRA. Outro contrato n.º 999999999999.""")
    assert dados["registroGarantia"] == "R.03"
    assert dados["titulo"].startswith("Contrato de Compra e Venda de Imóvel")


def test_pdf_com_caracteres_ilegiveis_exige_revisao():
    oficio = OFICIO.replace("CAIXA ECONÔMICA", "CAIXA ECON�MICA")
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", side_effect=[oficio, PROJECAO]):
        dados = analisar_pdfs_intimacao(
            b"%PDF oficio", b"%PDF projecao", date(2026, 10, 9), "IN01688738C"
        )
    assert any("caracteres ilegíveis" in aviso for aviso in dados["avisos"])


def test_simbolo_ordinal_ilegivel_no_endereco_e_corrigido_sem_adivinhar_nome():
    oficio = OFICIO.replace("nº51", "n�51")
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", side_effect=[oficio, PROJECAO]):
        dados = analisar_pdfs_intimacao(
            b"%PDF oficio", b"%PDF projecao", date(2026, 10, 9), "IN01688738C"
        )
    assert "n.º 51" in dados["enderecos"][0]
    assert "�" not in dados["enderecos"][0]


def test_dois_devedores_e_dois_enderecos_nao_sao_mesclados():
    oficio = """Ofício nº 217507/2026
    1. CAIXA ECONÔMICA FEDERAL - CNPJ 00.360.305/0001-04
    Fiduciante(s): PESSOA PRIMEIRA - CPF: 11111111111; PESSOA SEGUNDA - CPF: 22222222222
    Matrícula(s): 30338
    Contrato: 844441753253, firmado em:18/01/2018
    3. Endereços indicados pelo credor:
    Rua das Flores, nº 11, Centro, MORRINHOS/GO, CEP 75650082
    Avenida Brasil, nº 22, Jardim América, MORRINHOS/GO, CEP 75650292
    3.1 Outras diligências
    """
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", side_effect=[oficio, PROJECAO]):
        dados = analisar_pdfs_intimacao(
            b"%PDF oficio", b"%PDF projecao", date(2026, 10, 9), "IN01688738C"
        )
    assert len(dados["devedores"]) == 2
    assert len(dados["enderecos"]) == 2


def test_pdf_unico_rtd_extrai_dois_devedores_e_dois_enderecos():
    texto = """Ofício INT/2026/043 - IN01688738C
    Ao Ilmo Sr. ANA PEREIRA (CPF: 111.111.111-11).
    Ao Ilmo Sr. BRUNO COSTA (CPF: 222.222.222-22).
    Endereço para notificação:
    1) Rua A, n.º 123, Lote 1, Centro, Morrinhos-GO, CEP: 75650-082.
    2) Rua B, Lote 2, Jardim, Morrinhos-GO, CEP: 75654-340.
    OBSERVAÇÕES:
    O devedor pode ser encontrado em RUA B, - S/N - LOTE 2 - MORRINHOS - GO.
    """
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", return_value=texto):
        dados = extrair_dados_documento_rtd(b"%PDF combinado", "IN01688738C")
    assert len(dados["devedores"]) == 2
    assert len(dados["enderecos"]) == 2
    assert dados["enderecos"][0]["numero"] == "123"
    assert dados["enderecos"][1]["numero"] == "S/N"


def test_pdf_rtd_aceita_mesmo_cpf_com_nome_apenas_sem_acento():
    texto = """Ofício INT/2026/043 - IN01688738C
    Ao Ilmo Sr. ROGÉRIO CARLOS MACHADO (CPF: 944.390.951-00).
    Fiduciante(s): ROGERIO CARLOS MACHADO - CPF:94439095100, Solteiro
    Matrícula(s): 30338
    Endereço para notificação:
    1) Rua A, n.º 123, Centro, Morrinhos-GO, CEP: 75650-082.
    OBSERVAÇÕES:
    """
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", return_value=texto):
        dados = extrair_dados_documento_rtd(b"%PDF combinado", "IN01688738C")
    assert dados["devedores"] == [{"nome": "ROGERIO CARLOS MACHADO", "cpf": "94439095100"}]


def test_pdf_rtd_rejeita_nomes_realmente_diferentes_para_o_mesmo_cpf():
    texto = """Ofício INT/2026/043 - IN01688738C
    Ao Ilmo Sr. ROGÉRIO CARLOS MACHADO (CPF: 944.390.951-00).
    Fiduciante(s): OUTRA PESSOA - CPF:94439095100
    Matrícula(s): 30338
    """
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", return_value=texto):
        try:
            extrair_dados_documento_rtd(b"%PDF combinado", "IN01688738C")
        except ErroDocumentoIntimacao as erro:
            assert "nomes diferentes para o mesmo CPF" in str(erro)
        else:
            raise AssertionError("Nomes diferentes para o mesmo CPF foram aceitos")


def test_pdf_rtd_com_outro_in_e_rejeitado():
    with patch("backend.app.servicos.documentos_intimacao._ler_pdf", return_value="IN01688738C"):
        try:
            extrair_dados_documento_rtd(b"%PDF combinado", "IN01686990C")
        except ErroDocumentoIntimacao as erro:
            assert "outro número de IN" in str(erro)
        else:
            raise AssertionError("O PDF de outro IN foi aceito")


def test_extracao_do_pdf_rtd_exige_sessao_e_csrf():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.database import preparar_banco
    from backend.app.rotas.intimacoes import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[preparar_banco] = lambda: None
    with TestClient(app) as client:
        resposta = client.post(
            "/api/intimacoes/00000000-0000-0000-0000-000000000001/extrair-documento-rtd",
            files={"arquivo": ("Documentos RTD.pdf", b"%PDF teste", "application/pdf")},
        )
    assert resposta.status_code in (401, 403)
