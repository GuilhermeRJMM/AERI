from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor

router = APIRouter(prefix='/api/rtd-intimacoes', tags=['RTD'], dependencies=[Depends(preparar_banco)])


@router.get('/status')
def status(_usuario=Depends(exigir_permissao('ver_intimacoes'))):
    with conectar() as con, con.cursor() as cur:
        cur.execute('SELECT * FROM rtd_sincronizacao_aeri WHERE id=1')
        config = cur.fetchone()
        cur.execute('''SELECT COUNT(*) AS total,
            COUNT(*) FILTER (WHERE intimacao_id IS NOT NULL) AS vinculados,
            COUNT(*) FILTER (WHERE pendente) AS fila,
            COUNT(*) FILTER (WHERE erro IS NOT NULL) AS falhas,
            COUNT(*) FILTER (WHERE intimacao_id IS NULL AND NOT pendente) AS sem_vinculo
            FROM rtd_pedidos_aeri''')
        contagens = cur.fetchone()
        cur.execute('''SELECT protocolo,in_documento,vinculo,erro FROM rtd_pedidos_aeri
            WHERE erro IS NOT NULL OR vinculo IN ('IN_AMBIGUO','CONFLITO','IN_NAO_CADASTRADO','SEM_IN')
            ORDER BY alterado_em DESC LIMIT 30''')
        revisao = cur.fetchall()
    return {'sincronizacao': config, 'contagens': contagens, 'revisao': revisao, 'intervaloMinutos': 5}


class Leitura(BaseModel):
    versao: int = Field(ge=1)


@router.post('/{protocolo}/lido', dependencies=[Depends(proteger_csrf)])
def marcar_lido(protocolo: str, dados: Leitura, request: Request,
                usuario=Depends(exigir_permissao('ver_intimacoes'))):
    with conectar() as con, con.cursor() as cur:
        cur.execute('''SELECT p.versao FROM rtd_pedidos_aeri p JOIN intimacoes_aeri i ON i.id=p.intimacao_id
            WHERE p.protocolo=%s AND i.excluida_em IS NULL''', (protocolo,))
        atual = cur.fetchone()
        if not atual:
            raise HTTPException(404, 'Protocolo RTD vinculado não encontrado.')
        if dados.versao > atual['versao']:
            raise HTTPException(409, 'Recarregue a intimação antes de marcar o aviso como visto.')
        # Marca só a versão que a pessoa viu: uma mudança concorrente continuará destacada.
        cur.execute('''INSERT INTO rtd_leituras_aeri(protocolo,usuario,versao) VALUES (%s,%s,%s)
            ON CONFLICT(protocolo,usuario) DO UPDATE SET
            versao=GREATEST(rtd_leituras_aeri.versao,EXCLUDED.versao),lido_em=NOW()''',
            (protocolo, usuario, dados.versao))
        registrar_auditoria_cursor(cur, request, 'rtd_aviso_lido', 'sucesso', usuario)
        con.commit()
    return {'ok': True}
