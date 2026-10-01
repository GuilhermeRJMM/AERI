"""Reconcilia relatório XLS autorizado. Prévia por padrão; exclusão é sempre lixeira."""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import uuid4

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto).lower()) if not unicodedata.combining(c)).strip()


def em_tratativa(status):
    status = normalizar(status)
    return not (status.startswith('arquiv') or status == 'desistencia concluida'
                or status in ('registro / averbacao', 'entrega das importancias recebidas'))


def ler_relatorio(caminho):
    import xlrd  # Dependência somente deste importador de Excel antigo.
    livro = xlrd.open_workbook(str(caminho), logfile=io.StringIO())
    folha = livro.sheet_by_index(0)
    cabecalho = next(i for i in range(folha.nrows) if folha.cell_value(i, 0) == 'Protocolo')
    nomes = folha.row_values(cabecalho)
    col = {v: nomes.index(v) for v in ('Protocolo','Solicitante','Prenotação','Status','Assunto','Data Status')}
    registros = {}
    for i in range(cabecalho + 1, folha.nrows):
        valores = folha.row_values(i)
        p = str(valores[col['Protocolo']]).strip().upper()
        if not re.fullmatch(r'IN\d{8}C', p):
            continue
        registro = {chave:str(valores[pos]).strip() for chave,pos in col.items()}
        if p in registros and registros[p] != registro:
            raise ValueError(f'Protocolo repetido com dados diferentes: {p}')
        registros[p] = registro
    return registros


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arquivo', type=Path)
    parser.add_argument('--esperados', type=int, required=True)
    parser.add_argument('--arquivar', nargs='*', default=[])
    parser.add_argument('--aplicar', action='store_true')
    parser.add_argument('--usuario', help='Responsável registrado na auditoria (administrador existente).')
    args = parser.parse_args()
    from scripts.sincronizar_rtd import carregar_ambiente
    carregar_ambiente()
    from backend.app.database import conectar, fechar_pool
    from backend.app.servicos.intimacoes import fase_por_andamento
    from psycopg.types.json import Jsonb
    from backend.app.seguranca_web import registrar_auditoria_cursor
    todos = ler_relatorio(args.arquivo)
    ativos = {p:r for p,r in todos.items() if em_tratativa(r['Status'])}
    if len(ativos) != args.esperados:
        raise ValueError(f'Relatório resultou em {len(ativos)}, não {args.esperados}. Nada alterado.')
    assinatura = hashlib.sha256(args.arquivo.read_bytes()).hexdigest()
    try:
        with conectar() as con, con.cursor() as cur:
            cur.execute('LOCK TABLE intimacoes_aeri IN SHARE ROW EXCLUSIVE MODE')
            cur.execute('SELECT * FROM intimacoes_aeri WHERE excluida_em IS NULL')
            atuais = {r['protocolo']:r for r in cur.fetchall()}
            novos = sorted(set(ativos)-set(atuais))
            remover = sorted(set(atuais)-set(ativos))
            if set(remover) != set(args.arquivar):
                raise ValueError('Diferença na lista de arquivamento autorizado. Execute a prévia com a lista exata.')
            print(json.dumps({'relatorio':len(todos),'em_tratativa':len(ativos),'incluir':novos,
                              'lixeira':remover,'preservados':len(set(atuais)&set(ativos))},ensure_ascii=False))
            if not args.aplicar:
                con.rollback(); return
            usuario = args.usuario or os.getenv('AERI_ADMIN_USER')
            cur.execute("SELECT usuario FROM usuarios_aeri WHERE usuario=%s AND ativo=TRUE AND perfil IN ('ADMIN','SUBSTITUTO')",(usuario,))
            if not cur.fetchone():
                raise ValueError('Administrador responsável não identificado no ambiente.')
            for p in novos:
                r=ativos[p]
                cur.execute('''SELECT DISTINCT nome FROM rtd_pedidos_aeri,
                    jsonb_array_elements_text(destinatarios) AS nome
                    WHERE in_documento=%s AND jsonb_array_length(candidatos)=1 ORDER BY nome''',(p,))
                nomes = [x['nome'] for x in cur.fetchall()]
                devedor = '; '.join(nomes)
                if not devedor or len(devedor)>160:
                    devedor = 'Aguardando identificação no documento RTD'
                data = datetime.strptime(r['Data Status'],'%d/%m/%Y').date()
                fase = fase_por_andamento(r['Status']+' '+r['Assunto'])
                identificador = uuid4()
                cur.execute('''INSERT INTO intimacoes_aeri
                    (id,protocolo,credor,devedor,nome_andamento,ultimo_andamento,fase,protocolo_tri7,
                     valor_pago_onr,valor_usado,devedor_rtd_valor)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s)''',
                    (identificador,p,r['Solicitante'],devedor,r['Status'],data,fase,r['Prenotação'] or None,
                     devedor if nomes and len('; '.join(nomes))<=160 else None))
                cur.execute('''INSERT INTO eventos_intimacao_aeri(intimacao_id,protocolo,tipo,usuario,detalhes)
                    VALUES (%s,%s,'CRIACAO',%s,%s)''', (identificador,p,usuario,Jsonb({'fonte':'relatorio_oficio_eletronico','sha256':assinatura})))
            for p in remover:
                cur.execute('''UPDATE intimacoes_aeri SET excluida_em=NOW(),excluida_por=%s,atualizado_em=NOW()
                    WHERE id=%s''',(usuario,atuais[p]['id']))
                cur.execute('''INSERT INTO eventos_intimacao_aeri(intimacao_id,protocolo,tipo,usuario,detalhes)
                    VALUES (%s,%s,'EXCLUSAO',%s,%s)''',(atuais[p]['id'],p,usuario,
                    Jsonb({'motivo':'reconciliacao_autorizada_relatorio','sha256':assinatura,'restauravel':True})))
            cur.execute('SELECT protocolo FROM intimacoes_aeri WHERE excluida_em IS NULL')
            if {r['protocolo'] for r in cur.fetchall()} != set(ativos):
                raise ValueError('Conferência final divergente. Transação revertida.')
            # Os 31 existentes devem permanecer byte a byte intactos.
            cur.execute('SELECT * FROM intimacoes_aeri WHERE protocolo=ANY(%s)',(list(set(atuais)&set(ativos)),))
            if any(r != atuais[r['protocolo']] for r in cur.fetchall()):
                raise ValueError('Dado existente foi alterado. Transação revertida.')
            cur.execute('''UPDATE rtd_pedidos_aeri SET pendente=TRUE,tentar_em=NOW()
                WHERE in_documento=ANY(%s)''',(novos,))
            registrar_auditoria_cursor(cur,None,'importar_intimacoes_relatorio','sucesso',usuario,
                detalhes={'incluidos':len(novos),'lixeira':len(remover),'total':len(ativos),'sha256':assinatura})
            con.commit()
            print(f'Confirmado no banco: {len(ativos)} ativas. Histórico preservado; exclusões restauráveis.')
    finally:
        fechar_pool()


if __name__ == '__main__':
    main()
