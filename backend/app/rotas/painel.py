from fastapi import APIRouter, Depends, Request

from backend.app.autenticacao import exigir_permissao
from backend.app.database import conectar, preparar_banco


router = APIRouter(
    prefix="/api/painel",
    tags=["painel"],
    dependencies=[Depends(preparar_banco)],
)


@router.get("")
def obter_painel(request: Request, _usuario: str = Depends(exigir_permissao("ver_intimacoes"))):
    administrativo = request.state.sessao["perfil"] in {"ADMIN", "SUBSTITUTO"}
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE fase='INTIMACAO') AS intimacao,
                    COUNT(*) FILTER (WHERE fase='EDITAL') AS edital,
                    COUNT(*) FILTER (WHERE fase='CONSOLIDACAO') AS consolidacao,
                    COUNT(*) FILTER (
                        WHERE data_certificacao IS NOT NULL AND data_certificacao < CURRENT_DATE
                    ) AS certificacoes_vencidas,
                    COUNT(*) FILTER (
                        WHERE ultima_conferencia IS NULL OR ultima_conferencia < CURRENT_DATE
                    ) AS conferencias_pendentes
                FROM intimacoes_aeri"""
            )
            resumo = cursor.fetchone()
            cursor.execute(
                """SELECT id, protocolo, fase, nome_andamento, ultimo_andamento,
                data_certificacao, ultima_conferencia
                FROM intimacoes_aeri
                WHERE (data_certificacao IS NOT NULL AND data_certificacao <= CURRENT_DATE + 3)
                   OR ultima_conferencia IS NULL OR ultima_conferencia < CURRENT_DATE
                ORDER BY data_certificacao NULLS LAST, ultimo_andamento NULLS FIRST
                LIMIT 30"""
            )
            pendencias = cursor.fetchall()
            divergencias = 0
            if administrativo:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM divergencias_analise_aeri WHERE status='PENDENTE'"
                )
                divergencias = cursor.fetchone()["total"]
    return {
        "resumo": {**resumo, "divergencias_pendentes": divergencias},
        "pendencias": [
            {
                "id": str(item["id"]),
                "protocolo": item["protocolo"],
                "fase": item["fase"],
                "nome_andamento": item["nome_andamento"],
                "ultimo_andamento": item["ultimo_andamento"].isoformat() if item["ultimo_andamento"] else None,
                "data_certificacao": item["data_certificacao"].isoformat() if item["data_certificacao"] else None,
                "ultima_conferencia": item["ultima_conferencia"].isoformat() if item["ultima_conferencia"] else None,
            }
            for item in pendencias
        ],
    }
