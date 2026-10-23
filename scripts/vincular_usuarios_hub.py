"""Vínculos administrados por documento fornecido pelo responsável, não por JWT."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend.app.database import conectar, fechar_pool


def ler_documento(caminho):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(caminho) as z:
        if z.getinfo("word/document.xml").file_size > 4_000_000:
            raise ValueError("Documento excede o limite de leitura.")
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    tabelas = root.findall(".//w:tbl", ns)
    if len(tabelas) != 1:
        raise ValueError("Esperada uma única tabela de vínculos.")
    linhas = [["".join(t.text or "" for t in cel.findall(".//w:t", ns)).strip()
               for cel in tr.findall("w:tc", ns)] for tr in tabelas[0].findall("w:tr", ns)]
    if not linhas or linhas[0] != ["Login do HUB", "Situação no HUB", "Identificador SSO"]:
        raise ValueError("Cabeçalho de vínculos não reconhecido.")
    registros = []
    for linha in linhas[1:]:
        if len(linha) != 3 or not linha[0] or linha[1] not in {"Ativa", "Primeiro acesso pendente"}:
            raise ValueError("Linha de vínculo inválida.")
        sub = str(UUID(linha[2]))
        if sub != linha[2]:
            raise ValueError("UUID não canônico.")
        registros.append({"usuario": linha[0].upper(), "sub": sub})
    if len({r["sub"] for r in registros}) != len(registros) or len({r["usuario"] for r in registros}) != len(registros):
        raise ValueError("Identidades repetidas no documento.")
    return registros, hashlib.sha256(xml).hexdigest()


def executar(caminho, aplicar=False):
    registros, fingerprint = ler_documento(caminho)
    lote = str(uuid4())
    resumo = {"aplicado": aplicar, "total_documento": len(registros), "vinculados": 0,
              "ja_vinculados": 0, "pendentes": {}, "lote": lote if aplicar else None}
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as c:
            # Não permite trocar a identidade local ou reativar conta nesta operação.
            if aplicar:
                c.execute("LOCK TABLE usuarios_aeri IN SHARE ROW EXCLUSIVE MODE")
                c.execute((Path(__file__).resolve().parents[1] / "backend/app/migrations/063_sso_hub.sql").read_text(encoding="utf-8"))
                c.execute("LOCK TABLE vinculos_sso_hub_aeri IN SHARE ROW EXCLUSIVE MODE")
            tem_tabela = c.execute("SELECT to_regclass('vinculos_sso_hub_aeri') AS tabela").fetchone()["tabela"]
            contas = {r["usuario"]: r for r in c.execute("""SELECT u.usuario,u.ativo,i.id_sync
                FROM usuarios_aeri u LEFT JOIN importacoes_usuarios_sync_aeri i
                ON i.usuario=u.usuario AND i.origem='cartorio_tvcopa'""").fetchall()}
            existentes = c.execute("SELECT subject,usuario FROM vinculos_sso_hub_aeri WHERE emissor='sync-hub'").fetchall() if tem_tabela else []
            por_sub = {str(r["subject"]): r["usuario"] for r in existentes}
            por_usuario = {r["usuario"]: str(r["subject"]) for r in existentes}
            for r in registros:
                conta = contas.get(r["usuario"])
                motivo = ("sem_conta" if not conta else "conta_inativa" if not conta["ativo"]
                          else "identidade_local_nao_reconciliada" if conta["id_sync"] is None else None)
                if por_sub.get(r["sub"], r["usuario"]) != r["usuario"] or por_usuario.get(r["usuario"], r["sub"]) != r["sub"]:
                    motivo = "vinculo_conflitante"
                if motivo:
                    resumo["pendentes"][motivo] = resumo["pendentes"].get(motivo, 0) + 1
                    continue
                if r["sub"] in por_sub:
                    resumo["ja_vinculados"] += 1
                    continue
                if aplicar:
                    c.execute("INSERT INTO vinculos_sso_hub_aeri (emissor,subject,usuario) VALUES ('sync-hub',%s,%s)", (r["sub"], r["usuario"]))
                    c.execute("""INSERT INTO auditoria_aeri (acao,recurso,resultado,detalhes)
                        VALUES ('vincular_usuario_hub',%s,'sucesso',%s)""",
                        (r["usuario"], Jsonb({"lote": lote, "documento_fingerprint": fingerprint,
                                             "emissor": "sync-hub", "id_sync": conta["id_sync"]})))
                resumo["vinculados"] += 1
            if aplicar: db.commit()
            else: db.rollback()
    return resumo


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--documento", required=True)
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()
    try:
        print(json.dumps(executar(args.documento, args.aplicar), ensure_ascii=False))
    finally:
        fechar_pool()
