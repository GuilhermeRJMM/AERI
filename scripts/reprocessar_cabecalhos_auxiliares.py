"""Repara números explícitos com texto da Tri7. Prévia padrão; sem segredos na saída."""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def carregar_executor(diretorio):
    from dotenv import dotenv_values
    permitidas = {'POSTGRES_URL','DATABASE_URL','TRI7_API_BASE_URL','TRI7_API_USERNAME',
                  'TRI7_API_PASSWORD','TRI7_API_ACCESS_TOKEN','AERI_HASH_REMOTO_TOKEN','AERI_BUSCAS_HMAC_KEY'}
    for nome in ('.env', '.env.buscas.local'):
        for chave, valor in dotenv_values(diretorio / nome).items():
            if chave in permitidas and valor and '[SENSITIVE]' not in valor:
                os.environ.setdefault(chave, valor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executor-dir', type=Path, required=True)
    parser.add_argument('--numeros', type=int, nargs='+', required=True)
    parser.add_argument('--pedidos', nargs='+', required=True)
    parser.add_argument('--usuario', required=True)
    parser.add_argument('--enfileirar-sem-pessoas', action='store_true')
    parser.add_argument('--reler-desde', type=int, default=1,
                        help='Limita os candidatos da fila sem interromper a revisão circular existente.')
    parser.add_argument('--aplicar', action='store_true')
    args = parser.parse_args()
    if any(n <= 0 for n in args.numeros) or len(set(args.numeros)) > 100 or args.reler_desde <= 0:
        raise ValueError('Informe de um a cem números positivos.')
    carregar_executor(args.executor_dir)
    from backend.app.database import conectar, fechar_pool
    from backend.app.servicos.tri7 import cliente_tri7
    from backend.app.servicos.registros_auxiliares import extrair_indice_registro_auxiliar
    from backend.app.servicos.custas import _registro_atende_custas
    from backend.app.servicos.buscas import hash_documento
    from backend.app.rotas.registros_auxiliares import _salvar_indice
    from backend.app.seguranca_web import registrar_auditoria_cursor
    from psycopg.types.json import Jsonb
    inicio = datetime.now(timezone.utc)
    textos = {n:cliente_tri7().buscar_texto_registro_auxiliar(n)['texto'] for n in sorted(set(args.numeros))}
    indices = {n:extrair_indice_registro_auxiliar(n,t) for n,t in textos.items()}
    try:
        with conectar() as con, con.cursor() as cur:
            cur.execute('SELECT usuario FROM usuarios_aeri WHERE usuario=%s AND ativo AND perfil IN (%s,%s)',
                        (args.usuario,'ADMIN','SUBSTITUTO'))
            if not cur.fetchone():
                raise ValueError('Administrador responsável inválido.')
            cur.execute('SELECT * FROM custas_livro3_aeri WHERE pedido=ANY(%s) FOR UPDATE', (args.pedidos,))
            pedidos = cur.fetchall()
            if {p['pedido'] for p in pedidos} != set(args.pedidos):
                raise ValueError('Pedido não encontrado. Nada alterado.')
            plano = []
            for pedido in pedidos:
                protegido = hash_documento(pedido['documento'])
                numeros = sorted(n for n,i in indices.items() if _registro_atende_custas(i,pedido,protegido))
                plano.append({'pedido':pedido['pedido'],'antes':pedido['resultado'],'registros_confirmados':numeros})
                if args.aplicar and pedido['resultado']=='NEGATIVA' and not pedido['finalizado'] and numeros:
                    if pedido['status'] not in {'FAZER_PESQUISA','BUSCA_REALIZADA','CUSTAS_INFORMADAS','PAGO_PROCESSANDO'}:
                        raise ValueError('Pedido fora do fluxo de revalidação. Nada alterado.')
                    status = 'CUSTAS_ERRADAS' if pedido['status'] in {'CUSTAS_INFORMADAS','PAGO_PROCESSANDO'} else 'BUSCA_REALIZADA'
                    cur.execute('''UPDATE custas_livro3_aeri SET resultado='POSITIVA',numero_registro=%s,
                        status=%s,negativa_insegura=FALSE,atualizado_por=%s,atualizado_em=NOW()
                        WHERE id=%s AND resultado='NEGATIVA' AND finalizado=FALSE''',
                        (', '.join(map(str,numeros)),status,args.usuario,pedido['id']))
                    cur.execute('''INSERT INTO eventos_custas_livro3_aeri(item_id,pedido,tipo,usuario,detalhes)
                        VALUES (%s,%s,'REVALIDACAO_INDICE',%s,%s)''',
                        (pedido['id'],pedido['pedido'],args.usuario,Jsonb({'motivo':'correcao_cabecalho_depositaria',
                         'resultadoAnterior':'NEGATIVA','resultadoAtual':'POSITIVA','statusAnterior':pedido['status'],
                         'statusAtual':status,'registros':numeros})))
            print(json.dumps({'previa':not args.aplicar,'pessoas_por_registro':{n:len(i['pessoas']) for n,i in indices.items()},
                              'pedidos':plano},ensure_ascii=True))
            if not args.aplicar:
                cur.execute("""SELECT COUNT(*) AS total FROM registros_auxiliares_aeri
                    WHERE pessoas='[]'::jsonb AND situacao='ATIVO' AND modalidade IN ('PENHOR','ALIENAÇÃO')
                    AND (produtos<>'[]'::jsonb OR safras<>'[]'::jsonb) AND numero >= %s""", (args.reler_desde,))
                print(json.dumps({'candidatos_sem_pessoas':cur.fetchone()['total']}))
                con.rollback()
                return
            for numero, texto in textos.items():
                _salvar_indice(cur, numero, texto, solicitada_ate=inicio)
            enfileirados = 0
            if args.enfileirar_sem_pessoas:
                cur.execute('''INSERT INTO fila_registros_auxiliares_aeri(numero,motivo)
                    SELECT numero,'CABECALHO_GENERO_20261029' FROM registros_auxiliares_aeri
                    WHERE pessoas='[]'::jsonb AND situacao='ATIVO' AND modalidade IN ('PENHOR','ALIENAÇÃO')
                    AND (produtos<>'[]'::jsonb OR safras<>'[]'::jsonb) AND numero >= %s
                    ON CONFLICT(numero) DO UPDATE SET motivo=EXCLUDED.motivo,
                    proxima_tentativa_em=LEAST(fila_registros_auxiliares_aeri.proxima_tentativa_em,NOW())''',
                    (args.reler_desde,))
                enfileirados = cur.rowcount
            registrar_auditoria_cursor(cur,None,'reprocessar_cabecalhos_auxiliares','sucesso',args.usuario,
                detalhes={'numeros':sorted(textos),'pedidos':args.pedidos,'enfileirados':enfileirados})
            con.commit()
            print(json.dumps({'aplicado':True,'enfileirados_para_releitura':enfileirados}))
    finally:
        fechar_pool()


if __name__ == '__main__':
    try:
        main()
    except Exception as erro:
        print('Operação não concluída; tipo da falha: '+type(erro).__name__,file=sys.stderr)
        raise SystemExit(1)
