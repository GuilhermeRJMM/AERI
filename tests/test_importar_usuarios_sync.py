import sqlite3
from scripts.importar_usuarios_sync import ler_sync, planejar


def conta(id=1, login="pessoa", nome="Pessoa Teste", ativo=1):
    return {"id": id, "login": login, "nome": nome, "ativo": ativo}


def test_novo_preserva_estado_e_normaliza_login():
    p = planejar([conta(login=" pessoa ", ativo=0)], [])[0]
    assert p["usuario"] == "PESSOA" and not p["ativo"] and not p["motivos"]


def test_nao_une_por_nome_nem_sobrescreve_login():
    atuais = [{"usuario": "OUTRO", "nome": "Pessoa Teste"}]
    assert planejar([conta()], atuais)[0]["motivos"] == ["nome_ja_existe_outro_login"]
    assert planejar([conta(login="outro")], atuais)[0]["motivos"] == ["login_existente"]


def test_duplicados_e_invalidos_nao_entram():
    p = planejar([conta(), conta(id=2, login="PESSOA"), conta(id=3, login="in válido")], [])
    assert all(r["motivos"] for r in p)


def test_reexecucao_nao_altera_origem_existente():
    anterior = [{"id_sync": 1, "usuario": "PESSOA"}]
    assert planejar([conta()], [], anterior)[0]["motivos"] == ["ja_importado"]
    assert planejar([conta(login="mudou")], [], anterior)[0]["motivos"] == ["origem_alterada"]


def test_leitura_nao_le_senhas_ou_permissoes(tmp_path):
    p = tmp_path / "origem.db"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE usuarios (id INTEGER,nome TEXT,login TEXT,ativo INTEGER,senha TEXT,permissoes TEXT)")
        c.execute("INSERT INTO usuarios VALUES (1,'Pessoa','pessoa',1,'nao-ler','nao-importar')")
    assert ler_sync(p) == [conta(nome="Pessoa")]
