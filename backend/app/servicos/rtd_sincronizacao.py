"""Fila persistente RTD, retomável e independente da conferência interna."""
import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from backend.app.database import conectar
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.rtd_cliente import ClienteRTD, ErroRTD, extrair_documento_pdf, hash_resumo, retrato

INTERVALO_MINUTOS = 5
TRAVA = 1_095_062_145


def decidir_vinculo(ins, correspondencias, legado, atual=None):
    """Só vincula por IN exato; referências conflitantes nunca escolhem o primeiro."""
    if len(ins) > 1:
        return atual, 'IN_AMBIGUO'
    encontrados = correspondencias if len(ins) == 1 else legado
    if len(encontrados) != 1:
        return atual, 'IN_NAO_CADASTRADO' if ins else 'SEM_IN'
    alvo = encontrados[0]
    if (atual and str(atual) != str(alvo)) or any(str(x) != str(alvo) for x in legado):
        return atual, 'CONFLITO'
    return alvo, 'DOCUMENTO' if ins else 'CADASTRO_EXISTENTE'


def salvar_pedido(cursor, anterior, dados, cliente):
    protocolo = anterior['protocolo']
    novo = retrato(dados)
    url = dados.get('UrlArquivoEnviado') or ''
    documento_hash = hashlib.sha256(('destinatarios-v2:' + url).encode()).hexdigest()
    ins = anterior.get('candidatos') or []
    destinatarios = anterior.get('destinatarios') or []
    consulta = anterior.get('consultado_em')
    vencido = consulta and consulta < datetime.now(timezone.utc) - timedelta(days=1)
    if url and (documento_hash != anterior.get('documento_hash') or anterior['erro'] or vencido):
        documento = extrair_documento_pdf(cliente.baixar(url))
        ins, destinatarios = documento['ins'], documento['destinatarios']
    elif not url:
        ins = []
        destinatarios = []
    cursor.execute('SELECT id FROM intimacoes_aeri WHERE protocolo=ANY(%s) AND excluida_em IS NULL', (ins,))
    correspondencias = [x['id'] for x in cursor.fetchall()]
    cursor.execute('SELECT id FROM intimacoes_aeri WHERE protocolo_rtd=%s AND excluida_em IS NULL', (protocolo,))
    legado = [x['id'] for x in cursor.fetchall()]
    alvo, vinculo = decidir_vinculo(ins, correspondencias, legado, anterior.get('intimacao_id'))
    mudou = (novo != anterior['dados'] or alvo != anterior.get('intimacao_id')
             or vinculo != anterior['vinculo'] or destinatarios != (anterior.get('destinatarios') or []))
    versao = anterior['versao'] + int(mudou)
    if mudou:
        cursor.execute('''INSERT INTO rtd_eventos_aeri(protocolo,versao,anterior,atual)
            VALUES (%s,%s,%s,%s)''', (protocolo, versao, Jsonb(anterior['dados']), Jsonb(novo)))
    cursor.execute('''UPDATE rtd_pedidos_aeri SET intimacao_id=%s, in_documento=%s,
        candidatos=%s, destinatarios=%s, vinculo=%s, dados=%s, documento_hash=%s, versao=%s,
        pendente=FALSE, erro=NULL, consultado_em=NOW(),
        alterado_em=CASE WHEN %s THEN NOW() ELSE alterado_em END WHERE protocolo=%s''',
        (alvo, ins[0] if len(ins) == 1 else None, Jsonb(ins), Jsonb(destinatarios), vinculo, Jsonb(novo),
         documento_hash, versao, mudou, protocolo))
    if alvo and vinculo == 'DOCUMENTO' and destinatarios:
        # Preenche apenas lacuna explícita de importação, jamais substitui dado humano.
        cursor.execute('''SELECT DISTINCT nome FROM rtd_pedidos_aeri p,
            jsonb_array_elements_text(p.destinatarios) AS nome
            WHERE p.intimacao_id=%s AND p.vinculo='DOCUMENTO' ORDER BY nome''', (alvo,))
        nomes = [r['nome'] for r in cursor.fetchall()]
        devedor = '; '.join(nomes)
        if len(devedor) <= 160:
            cursor.execute('''UPDATE intimacoes_aeri SET devedor=%s,devedor_rtd_valor=%s,atualizado_em=NOW()
                WHERE id=%s AND (devedor IN ('Não informado no relatório','Aguardando identificação no documento RTD')
                   OR devedor=devedor_rtd_valor) AND devedor IS DISTINCT FROM %s
                AND excluida_em IS NULL''', (devedor, devedor, alvo, devedor))
            if cursor.rowcount:
                registrar_auditoria_cursor(cursor,None,'rtd_identificar_devedor','sucesso',recurso=str(alvo))
    return bool(alvo), mudou


def executar_passo_rtd(cliente=None):
    if cliente is None and not os.getenv('AERI_RTD_TOKEN'):
        return {'estado': 'SEM_CONFIGURACAO'}
    cliente = cliente or ClienteRTD()
    agora = datetime.now(timezone.utc)
    resultado = {'estado': 'AGUARDANDO', 'processados': 0, 'vinculados': 0, 'alterados': 0}
    with conectar() as con:
        with con.cursor() as cur:
            # Trava transacional: liberada automaticamente, inclusive em falhas/crashes.
            cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS obteve', (TRAVA,))
            if not cur.fetchone()['obteve']:
                return {'estado': 'EM_EXECUCAO'}
            cur.execute('SELECT * FROM rtd_sincronizacao_aeri WHERE id=1')
            config = cur.fetchone()
            cur.execute('''INSERT INTO rtd_pedidos_aeri(protocolo)
                SELECT DISTINCT protocolo_rtd FROM intimacoes_aeri
                WHERE excluida_em IS NULL AND protocolo_rtd ~ '^[0-9]{17}$'
                ON CONFLICT DO NOTHING''')
            if not config['proxima_consulta'] or config['proxima_consulta'] <= agora:
                desde = config['desde']
                if not desde:
                    # Carga inicial completa: um processo antigo pode não ter mudanças recentes.
                    desde = date(2000, 1, 1)
                inicio = config['inicio_rodada'] or agora
                try:
                    pagina = cliente.atualizacoes(desde, config['pagina'])
                    for item in pagina['Data']:
                        cur.execute('''INSERT INTO rtd_pedidos_aeri(protocolo,resumo_hash)
                            VALUES (%s,%s) ON CONFLICT(protocolo) DO UPDATE SET
                            pendente=CASE WHEN rtd_pedidos_aeri.resumo_hash IS DISTINCT FROM EXCLUDED.resumo_hash
                                OR rtd_pedidos_aeri.intimacao_id IS NULL THEN TRUE ELSE rtd_pedidos_aeri.pendente END,
                            tentar_em=CASE WHEN rtd_pedidos_aeri.resumo_hash IS DISTINCT FROM EXCLUDED.resumo_hash
                                THEN NOW() ELSE rtd_pedidos_aeri.tentar_em END,
                            resumo_hash=EXCLUDED.resumo_hash''', (str(item['Protocolo']), hash_resumo(item)))
                    terminou = config['pagina'] >= pagina['TotalPages']
                    # Sobreposição de um dia, deduplicação por protocolo/hash e fila persistente.
                    # O cursor só avança após a página inteira estar registrada.
                    proximo_desde = (inicio.astimezone(ZoneInfo('America/Sao_Paulo')).date() - timedelta(days=1)) if terminou else desde
                    cur.execute('''UPDATE rtd_sincronizacao_aeri SET desde=%s,pagina=%s,
                        inicio_rodada=%s,proxima_consulta=%s,ultima_consulta=NOW(),
                        ultimo_sucesso=CASE WHEN %s THEN NOW() ELSE ultimo_sucesso END,
                        erro=NULL,atualizado_em=NOW() WHERE id=1''',
                        (proximo_desde, 1 if terminou else config['pagina'] + 1,
                         None if terminou else inicio, agora + timedelta(minutes=5) if terminou else agora, terminou))
                    resultado['estado'] = 'SINCRONIZANDO'
                except ErroRTD as exc:
                    cur.execute('''UPDATE rtd_sincronizacao_aeri SET erro=%s,ultima_consulta=NOW(),
                        proxima_consulta=%s,atualizado_em=NOW() WHERE id=1''',
                        (str(exc), agora + timedelta(minutes=1)))
                    resultado['estado'] = 'ERRO'
            # Reconsulta vínculos existentes pelo menos diariamente, mesmo sem mudança no resumo.
            cur.execute('''UPDATE rtd_pedidos_aeri SET pendente=TRUE
                WHERE NOT pendente AND (consultado_em < NOW()-INTERVAL '1 day'
                  OR (intimacao_id IS NULL AND in_documento IN
                     (SELECT protocolo FROM intimacoes_aeri WHERE excluida_em IS NULL)))''')
            cur.execute('''SELECT * FROM rtd_pedidos_aeri WHERE pendente AND tentar_em<=NOW()
                ORDER BY tentar_em,protocolo DESC LIMIT 2''')
            for item in cur.fetchall():
                try:
                    dados = cliente.pedido(item['protocolo'])
                    vinculado, mudou = salvar_pedido(cur, item, dados, cliente)
                    resultado['processados'] += 1
                    resultado['vinculados'] += int(vinculado)
                    resultado['alterados'] += int(mudou)
                except ErroRTD as exc:
                    cur.execute('''UPDATE rtd_pedidos_aeri SET erro=%s,tentar_em=NOW()+INTERVAL '30 minutes'
                        WHERE protocolo=%s''', (str(exc), item['protocolo']))
            if resultado['processados'] and resultado['estado'] == 'AGUARDANDO':
                resultado['estado'] = 'PROCESSANDO'
        con.commit()
    return resultado


def anexar_rtd(cursor, itens, usuario):
    """Leitura agregada, sem API externa e sem mudar o formato legado da listagem."""
    if not itens:
        return itens
    por_id = {str(item['id']): item for item in itens}
    for item in itens:
        item['rtd'] = []
    cursor.execute('''SELECT p.*, COALESCE(l.versao,0) AS versao_lida,
        COALESCE((SELECT jsonb_agg(e) FROM (
          SELECT anterior,atual,criado_em FROM rtd_eventos_aeri e WHERE e.protocolo=p.protocolo
          ORDER BY versao DESC LIMIT 10) e),'[]'::jsonb) AS eventos
        FROM rtd_pedidos_aeri p LEFT JOIN rtd_leituras_aeri l ON l.protocolo=p.protocolo AND l.usuario=%s
        WHERE p.intimacao_id=ANY(%s::uuid[]) ORDER BY p.alterado_em DESC''', (usuario, [item['id'] for item in itens]))
    for p in cursor.fetchall():
        por_id[str(p['intimacao_id'])]['rtd'].append({
            'protocolo': p['protocolo'], 'situacao': p['dados'].get('Situacao', 'Aguardando consulta'),
            'dados': p['dados'], 'versao': p['versao'], 'novo': p['versao'] > p['versao_lida'],
            'vinculo': p['vinculo'], 'erro': p['erro'], 'eventos': p['eventos'],
            'alteradoEm': p['alterado_em'].isoformat(),
            'consultadoEm': p['consultado_em'].isoformat() if p['consultado_em'] else None,
        })
    return itens
