"""Prioridades persistentes do Livro e das buscas, sem reiniciar o acervo."""


def enfileirar_auxiliares(cursor, numeros, motivo):
    for numero in sorted(set(n for n in numeros if isinstance(n, int) and n > 0)):
        cursor.execute(
            """INSERT INTO fila_registros_auxiliares_aeri(numero, motivo)
            VALUES (%s, %s) ON CONFLICT(numero) DO UPDATE SET
                motivo=EXCLUDED.motivo, solicitada_em=clock_timestamp(),
                proxima_tentativa_em=LEAST(fila_registros_auxiliares_aeri.proxima_tentativa_em, NOW())""",
            (numero, motivo[:40]),
        )


def concluir_auxiliar(cursor, numero, solicitada_ate):
    # Uma solicitação que chegou durante a consulta não pode ser descartada.
    cursor.execute(
        """DELETE FROM fila_registros_auxiliares_aeri
        WHERE numero=%s AND solicitada_em<=%s""", (numero, solicitada_ate),
    )


def reagendar_auxiliar(cursor, numero, minutos=15):
    cursor.execute(
        """UPDATE fila_registros_auxiliares_aeri
        SET proxima_tentativa_em=NOW()+make_interval(mins => %s)
        WHERE numero=%s AND solicitada_em<=transaction_timestamp()""",
        (minutos, numero),
    )
