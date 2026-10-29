"""Somente leitura. Usa a conexão configurada; nunca imprime DSN ou a pesquisa."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from backend.app.database import conectar, fechar_pool
    from backend.app.servicos.diagnostico_buscas import diagnosticar_cursor, medir_nome_cursor
    from backend.app.servicos.registros_auxiliares import normalizar_busca
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--medir-nome", action="store_true",
                        help="Solicita o nome interativamente, sem gravá-lo na linha de comando.")
    args = parser.parse_args()
    nome = ""
    if args.medir_nome:
        from getpass import getpass
        nome = normalizar_busca(getpass("Nome para medição (não será exibido): "))
        if len(nome) < 3:
            parser.error("Informe ao menos três caracteres.")
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '5s'")
                dados = diagnosticar_cursor(cursor)
                if nome:
                    dados["medicao"] = medir_nome_cursor(cursor, nome)
            conexao.rollback()
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    except Exception as erro:
        # Exceções do driver podem conter host, DSN ou parâmetros sensíveis.
        print(json.dumps({"erro": "Diagnóstico não concluído. Verifique a conexão e as permissões de leitura.",
                          "tipo": type(erro).__name__}, ensure_ascii=False))
        return 1
    finally:
        fechar_pool()


if __name__ == "__main__":
    raise SystemExit(main())
