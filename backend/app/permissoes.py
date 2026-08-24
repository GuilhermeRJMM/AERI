"""Catálogo e persistência centralizada das permissões do AERI.

As permissões deixam de ser colunas da tabela de usuários. O catálogo abaixo
é a única lista necessária para apresentar e validar uma atribuição nova; as
tabelas relacionais guardam concessões por perfil e por usuário.
"""

from __future__ import annotations

import json


CATALOGO_PERMISSOES = (
    {"chave": "processar_matricula", "nome": "Matrículas", "modulo": "Registro de Imóveis", "ordem": 10},
    {"chave": "revisar_auditoria", "nome": "Auditoria registral", "modulo": "Registro de Imóveis", "ordem": 20},
    {"chave": "acessar_mapa_onr", "nome": "MAPA-ONR", "modulo": "Registro de Imóveis", "ordem": 30, "auditor_opcional": True},
    {"chave": "acessar_livro_protocolos", "nome": "Livro de Protocolos", "modulo": "Registro de Imóveis", "ordem": 40, "auditor_opcional": True},
    {"chave": "acessar_buscas", "nome": "Buscas", "modulo": "Registro de Imóveis", "ordem": 50, "auditor_opcional": True},
    {"chave": "acessar_poligonos", "nome": "Polígonos", "modulo": "Registro de Imóveis", "ordem": 60, "auditor_opcional": True},
    {"chave": "acessar_gerador_notas", "nome": "Gerador de Notas", "modulo": "Registro de Imóveis", "ordem": 70},
    {"chave": "processar_incra", "nome": "INCRA", "modulo": "Rotinas", "ordem": 80},
    {"chave": "gerenciar_custas", "nome": "Informar Custas", "modulo": "Certidões", "ordem": 90},
    {"chave": "ver_intimacoes", "nome": "Ver intimações", "modulo": "Intimações", "ordem": 100},
    {"chave": "criar_intimacoes", "nome": "Criar/importar intimações", "modulo": "Intimações", "ordem": 110},
    {"chave": "alterar_intimacoes", "nome": "Alterar intimações", "modulo": "Intimações", "ordem": 120},
    {"chave": "conferir_intimacoes", "nome": "Dar check em intimações", "modulo": "Intimações", "ordem": 130},
)

# Compatibilidade temporária para rollback e para instalações que ainda não
# executaram a migração relacional. Nenhuma tela nova depende destas colunas.
COLUNAS_LEGADAS = {
    "processar_matricula": "pode_processar_matricula",
    "revisar_auditoria": "pode_revisar_auditoria",
    "acessar_mapa_onr": "pode_acessar_mapa_onr",
    "acessar_livro_protocolos": "pode_acessar_livro_protocolos",
    "acessar_buscas": "pode_acessar_buscas",
    "acessar_poligonos": "pode_acessar_poligonos",
    "acessar_gerador_notas": "pode_acessar_gerador_notas",
    "processar_incra": "pode_processar_incra",
    "gerenciar_custas": "pode_gerenciar_custas",
    "ver_intimacoes": "pode_ver_intimacoes",
    "criar_intimacoes": "pode_criar_intimacoes",
    "alterar_intimacoes": "pode_alterar_intimacoes",
    "conferir_intimacoes": "pode_conferir_intimacoes",
}

# Uma permissão futura pode entrar só no catálogo. A própria chave funciona
# como identificador até que exista (se necessário) uma coluna de rollback.
PERMISSOES = {
    item["chave"]: COLUNAS_LEGADAS.get(item["chave"], item["chave"])
    for item in CATALOGO_PERMISSOES
}
PERMISSOES_AUDITOR = {"processar_matricula", "revisar_auditoria"}
PERMISSOES_OPCIONAIS_AUDITOR = {
    item["chave"] for item in CATALOGO_PERMISSOES if item.get("auditor_opcional")
}


def catalogo_publico() -> list[dict]:
    return [
        {
            "chave": item["chave"],
            "nome": item["nome"],
            "modulo": item["modulo"],
            "ordem": item["ordem"],
            "auditorFixa": item["chave"] in PERMISSOES_AUDITOR,
            "auditorOpcional": item["chave"] in PERMISSOES_OPCIONAIS_AUDITOR,
        }
        for item in CATALOGO_PERMISSOES
    ]


def sincronizar_catalogo_cursor(cursor) -> None:
    """Mantém rótulos e regras de perfil sincronizados sem alterar concessões."""
    for item in CATALOGO_PERMISSOES:
        cursor.execute(
            """INSERT INTO permissoes_aeri (chave, nome, modulo, ordem, ativa)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (chave) DO UPDATE SET nome=EXCLUDED.nome,
            modulo=EXCLUDED.modulo, ordem=EXCLUDED.ordem, ativa=TRUE""",
            (item["chave"], item["nome"], item["modulo"], item["ordem"]),
        )
    cursor.execute("DELETE FROM perfis_permissoes_aeri WHERE perfil='AUDITOR'")
    cursor.executemany(
        """INSERT INTO perfis_permissoes_aeri (perfil, permissao)
        VALUES ('AUDITOR', %s) ON CONFLICT DO NOTHING""",
        [(chave,) for chave in sorted(PERMISSOES_AUDITOR)],
    )


def permissoes_relacionais_do_registro(registro: dict) -> set[str] | None:
    valor = registro.get("permissoes_relacionais")
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return set()
    if isinstance(valor, dict):
        return {chave for chave, concedida in valor.items() if concedida}
    if isinstance(valor, list):
        return {str(chave) for chave in valor}
    return set()


def selecionar_usuarios_com_permissoes(
    filtro: str = "",
    ordem: str = "u.ativo DESC, u.nome, u.usuario",
) -> str:
    """SELECT compartilhado por sessão e gestão, sem enumerar permissões."""
    return f"""SELECT u.*,
        COALESCE((
            SELECT jsonb_object_agg(chave, TRUE)
            FROM (
                SELECT pp.permissao AS chave
                FROM perfis_permissoes_aeri pp
                WHERE pp.perfil=u.perfil
                UNION
                SELECT up.permissao AS chave
                FROM usuarios_permissoes_aeri up
                WHERE up.usuario=u.usuario AND up.concedida=TRUE
            ) permissoes_efetivas
        ), '{{}}'::jsonb) AS permissoes_relacionais
        FROM usuarios_aeri u {filtro}{f' ORDER BY {ordem}' if ordem else ''}"""


def permissoes_efetivas_cursor(cursor, usuario: str, perfil: str) -> dict:
    cursor.execute(
        """SELECT permissao FROM perfis_permissoes_aeri WHERE perfil=%s
        UNION
        SELECT permissao FROM usuarios_permissoes_aeri
        WHERE usuario=%s AND concedida=TRUE""",
        (perfil, usuario),
    )
    return {item["permissao"]: True for item in cursor.fetchall()}


def substituir_permissoes_usuario_cursor(cursor, usuario: str, perfil: str, solicitadas: dict) -> None:
    validas = set(PERMISSOES)
    if perfil == "AUDITOR":
        validas = PERMISSOES_OPCIONAIS_AUDITOR
    elif perfil in {"ADMIN", "SUBSTITUTO"}:
        validas = set()
    concedidas = sorted(chave for chave in validas if bool(solicitadas.get(chave)))
    cursor.execute("DELETE FROM usuarios_permissoes_aeri WHERE usuario=%s", (usuario,))
    cursor.executemany(
        """INSERT INTO usuarios_permissoes_aeri (usuario, permissao, concedida)
        VALUES (%s, %s, TRUE) ON CONFLICT (usuario, permissao)
        DO UPDATE SET concedida=TRUE, atualizada_em=NOW()""",
        [(usuario, chave) for chave in concedidas],
    )
    # Escrita dupla durante a transição: permite rollback imediato e mantém
    # instâncias antigas de um deploy serverless coerentes até esfriarem.
    colunas = list(COLUNAS_LEGADAS.items())
    atribuicoes = ", ".join(f"{coluna}=%s" for _, coluna in colunas)
    cursor.execute(
        f"UPDATE usuarios_aeri SET {atribuicoes} WHERE usuario=%s",
        tuple(chave in concedidas or perfil in {"ADMIN", "SUBSTITUTO"} for chave, _ in colunas)
        + (usuario,),
    )


def definir_permissao_usuario_cursor(cursor, usuario: str, permissao: str, concedida: bool) -> None:
    if permissao not in PERMISSOES:
        raise KeyError(permissao)
    if concedida:
        cursor.execute(
            """INSERT INTO usuarios_permissoes_aeri (usuario, permissao, concedida)
            VALUES (%s, %s, TRUE) ON CONFLICT (usuario, permissao)
            DO UPDATE SET concedida=TRUE, atualizada_em=NOW()""",
            (usuario, permissao),
        )
    else:
        cursor.execute(
            "DELETE FROM usuarios_permissoes_aeri WHERE usuario=%s AND permissao=%s",
            (usuario, permissao),
        )
    coluna_legada = COLUNAS_LEGADAS.get(permissao)
    if coluna_legada:
        cursor.execute(
            f"UPDATE usuarios_aeri SET {coluna_legada}=%s WHERE usuario=%s",
            (concedida, usuario),
        )
