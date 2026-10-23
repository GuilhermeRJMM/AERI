"""Importação conservadora de cadastro. Nunca lê senhas ou permissões Sync."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import unicodedata
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend.app.autenticacao import hash_senha
from backend.app.database import conectar, fechar_pool
from backend.app.permissoes import COLUNAS_LEGADAS

ORIGEM = "cartorio_tvcopa"


def normalizar_nome(valor):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(valor or ""))
                             if unicodedata.category(c) != "Mn").upper().split())


def ler_sync(caminho):
    # Manter a unidade mapeada: resolve() a transforma em URI UNC que o
    # SQLite Windows pode rejeitar como autoridade remota.
    with sqlite3.connect(Path(caminho).absolute().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        return [dict(r) for r in db.execute("SELECT id,nome,login,ativo FROM usuarios ORDER BY id")]


def planejar(origem, existentes, importados=()):
    logins = Counter(str(r["login"] or "").strip().upper() for r in origem)
    nomes_origem = Counter(normalizar_nome(r["nome"]) for r in origem)
    contas = {r["usuario"].strip().upper(): r for r in existentes}
    nomes = {normalizar_nome(r["nome"]) for r in existentes}
    anteriores = {r["id_sync"]: r for r in importados}
    plano = []
    for r in origem:
        login = str(r["login"] or "").strip().upper()
        nome = str(r["nome"] or "").strip()
        motivos = []
        if not re.fullmatch(r"[A-Z0-9._-]{3,40}", login): motivos.append("login_invalido")
        if logins[login] > 1: motivos.append("login_repetido")
        if nomes_origem[normalizar_nome(nome)] > 1: motivos.append("nome_repetido_sync")
        if not nome or len(nome) > 160: motivos.append("nome_invalido")
        if r["ativo"] not in (0, 1): motivos.append("estado_ativo_invalido")
        anterior = anteriores.get(r["id"])
        if anterior:
            # A proveniência não autoriza trocar a identidade ou atualizar a conta.
            motivos.append("ja_importado" if anterior["usuario"] == login else "origem_alterada")
        elif login in contas:
            motivos.append("login_existente")
        elif normalizar_nome(nome) in nomes:
            motivos.append("nome_ja_existe_outro_login")
        plano.append({"id_sync": r["id"], "usuario": login, "nome": nome,
                      "ativo": r["ativo"] == 1, "motivos": motivos})
    return plano


def executar(caminho, aplicar=False):
    registros = ler_sync(caminho)
    fingerprint = hashlib.sha256(json.dumps(registros, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    lote = str(uuid4())
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as cursor:
            if aplicar:
                # Serializa a importação com criação/edição de contas da aplicação.
                cursor.execute("LOCK TABLE usuarios_aeri IN SHARE ROW EXCLUSIVE MODE")
                ddl = Path(__file__).resolve().parents[1] / "backend/app/migrations/064_importacao_usuarios_sync.sql"
                cursor.execute(ddl.read_text(encoding="utf-8"))
            existentes = cursor.execute("SELECT usuario,nome,ativo,perfil FROM usuarios_aeri ORDER BY usuario").fetchall()
            tem_tabela = cursor.execute("SELECT to_regclass('importacoes_usuarios_sync_aeri') AS tabela").fetchone()["tabela"]
            importados = cursor.execute("SELECT id_sync,usuario FROM importacoes_usuarios_sync_aeri WHERE origem=%s", (ORIGEM,)).fetchall() if tem_tabela else []
            plano = planejar(registros, existentes, importados)
            novos = [r for r in plano if not r["motivos"]]
            if aplicar:
                colunas = list(COLUNAS_LEGADAS.values())
                # Colunas vêm exclusivamente do catálogo interno, não do SQLite.
                for r in novos:
                    senha_descartada = hash_senha(secrets.token_urlsafe(48))
                    cursor.execute(
                        "INSERT INTO usuarios_aeri (usuario,nome,perfil,ativo,deve_trocar_senha,senha_hash,"
                        + ",".join(colunas) + ") VALUES (%s,%s,'USUARIO',%s,FALSE,%s,"
                        + ",".join("FALSE" for _ in colunas) + ")",
                        (r["usuario"], r["nome"], r["ativo"], senha_descartada),
                    )
                    cursor.execute("""INSERT INTO usuarios_permissoes_aeri (usuario,permissao,concedida)
                        SELECT %s,chave,FALSE FROM permissoes_aeri""", (r["usuario"],))
                    cursor.execute("""INSERT INTO importacoes_usuarios_sync_aeri
                        (origem,id_sync,usuario,lote,origem_fingerprint) VALUES (%s,%s,%s,%s,%s)""",
                        (ORIGEM, r["id_sync"], r["usuario"], lote, fingerprint))
                    cursor.execute("""INSERT INTO auditoria_aeri (acao,recurso,resultado,detalhes)
                        VALUES ('importar_usuario_sync',%s,'sucesso',%s)""",
                        (r["usuario"], Jsonb({"origem": ORIGEM, "id_sync": r["id_sync"], "lote": lote,
                                             "permissoes_concedidas": False})))
                depois = cursor.execute("SELECT usuario,nome,ativo,perfil FROM usuarios_aeri ORDER BY usuario").fetchall()
                anteriores = {r["usuario"]: r for r in existentes}
                if not all(r == anteriores[r["usuario"]] for r in depois if r["usuario"] in anteriores):
                    raise RuntimeError("A validação das contas anteriores falhou; transação cancelada.")
                usuarios_novos = [r["usuario"] for r in novos]
                if usuarios_novos:
                    concessoes = cursor.execute("SELECT COUNT(*) AS total FROM usuarios_permissoes_aeri WHERE usuario=ANY(%s) AND concedida=TRUE", (usuarios_novos,)).fetchone()["total"]
                    privilegiados = cursor.execute("SELECT COUNT(*) AS total FROM usuarios_aeri WHERE usuario=ANY(%s) AND (perfil<>'USUARIO' OR " + " OR ".join(colunas) + ")", (usuarios_novos,)).fetchone()["total"]
                    if concessoes or privilegiados:
                        raise RuntimeError("A validação de privilégio mínimo falhou; transação cancelada.")
            if aplicar: db.commit()
            else: db.rollback()
    return {"aplicado": aplicar, "lote": lote if aplicar else None, "total_sync": len(registros),
            "novos": len(novos), "ja_importados": sum(r["motivos"] == ["ja_importado"] for r in plano),
            "pendencias": [{"id_sync": r["id_sync"], "motivos": r["motivos"]} for r in plano
                           if r["motivos"] and r["motivos"] != ["ja_importado"]]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(executar(args.sqlite, args.aplicar), ensure_ascii=False))
    finally:
        fechar_pool()
