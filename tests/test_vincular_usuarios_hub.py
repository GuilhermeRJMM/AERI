from zipfile import ZipFile
from uuid import uuid4
from xml.sax.saxutils import escape
import pytest
from scripts.vincular_usuarios_hub import ler_documento


def documento(tmp_path, linhas):
    cabecalho = ["Login do HUB", "Situação no HUB", "Identificador SSO"]
    linhas = [cabecalho] + linhas
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>'
    for linha in linhas:
        xml += '<w:tr>' + ''.join('<w:tc><w:p><w:r><w:t>' + escape(c) + '</w:t></w:r></w:p></w:tc>' for c in linha) + '</w:tr>'
    xml += '</w:tbl></w:body></w:document>'
    p = tmp_path / "usuarios.docx"
    with ZipFile(p, "w") as z: z.writestr("word/document.xml", xml.encode())
    return p


def test_extrai_somente_mapeamento_validado(tmp_path):
    sub = str(uuid4())
    registros, fingerprint = ler_documento(documento(tmp_path, [["pessoa.teste", "Primeiro acesso pendente", sub]]))
    assert registros == [{"usuario": "PESSOA.TESTE", "sub": sub}]
    assert len(fingerprint) == 64


def test_uuid_duplicado_rejeita_documento_inteiro(tmp_path):
    sub = str(uuid4())
    with pytest.raises(ValueError):
        ler_documento(documento(tmp_path, [["pessoa1", "Ativa", sub], ["pessoa2", "Ativa", sub]]))


def test_login_repetido_com_uuid_diferente_rejeita(tmp_path):
    with pytest.raises(ValueError):
        ler_documento(documento(tmp_path, [["pessoa", "Ativa", str(uuid4())], ["PESSOA", "Ativa", str(uuid4())]]))


def test_uuid_invalido_nao_aceito(tmp_path):
    with pytest.raises(ValueError):
        ler_documento(documento(tmp_path, [["pessoa", "Ativa", "login-nao-e-sub"]]))
