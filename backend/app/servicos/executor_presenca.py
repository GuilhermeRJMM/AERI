"""Quem esta executando o trabalho de fundo: o executor da serventia ou a Vercel.

O executor roda numa maquina da serventia e nao tem endereco fixo nem porta
aberta -- ninguem consegue perguntar a ele se esta vivo. Entao ele mesmo diz, a
cada ciclo, gravando a hora no banco. Com isso o cron da Vercel sabe quando nao
precisa trabalhar, e a CPU cobrada por la deixa de ser gasta duas vezes.

A ausencia e resposta segura: sem batida recente, o cron assume o trabalho como
sempre fez. Executor desligado, maquina em manutencao ou serventia fechada nao
param a indexacao -- so a deixam mais lenta, no ritmo diario de antes.
"""
from backend.app.database import conectar

# Quanto tempo sem batida ate considerar o executor ausente. O ciclo padrao e de
# 15 segundos; 30 minutos toleram um lote lento, atualização de código e
# reinicialização. OCR não renova mais a presença da rotina ':indice'.
JANELA_MINUTOS = 30


def registrar_presenca(maquina: str, codigo_de=None, indexa=None) -> None:
    """Grava a batida. `indexa=None` preserva o que ja estava.

    O sincronizador usa uma identidade própria ':indice' e informa a capacidade
    de todas as fontes. O laço operacional não pode renovar essa presença.
    None continua compatível com executores anteriores durante a transição.
    """
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """INSERT INTO executores_aeri (maquina, visto_em, codigo_de, ciclos, indexa)
                VALUES (%s, NOW(), %s, 1, COALESCE(%s, FALSE))
                ON CONFLICT (maquina) DO UPDATE
                SET visto_em=NOW(), codigo_de=EXCLUDED.codigo_de,
                    ciclos=executores_aeri.ciclos + 1,
                    indexa=COALESCE(%s, executores_aeri.indexa)""",
                (maquina[:120], codigo_de, indexa, indexa),
            )
        conexao.commit()


def executor_ativo(cursor, minutos: int = JANELA_MINUTOS) -> bool:
    """Ha executor vivo E capaz de indexar.

    As duas coisas juntas de proposito. Um executor vivo mas sem a chave do
    indice na maquina nao substitui o cron: se ele bastasse para o cron se
    abster, a indexacao pararia dos dois lados e ninguem veria, porque nao ha
    erro nenhum -- so trabalho que deixa de acontecer.
    """
    cursor.execute(
        """SELECT EXISTS (SELECT 1 FROM executores_aeri
           WHERE indexa AND visto_em > NOW() - make_interval(mins => %s)) AS ativo""",
        (minutos,),
    )
    return bool(cursor.fetchone()["ativo"])
