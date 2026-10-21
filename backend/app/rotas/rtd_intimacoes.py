import os
import re
import hmac
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from starlette.responses import StreamingResponse
from urllib.parse import quote

from backend.app.autenticacao import (
    JANELA_TENTATIVAS_MINUTOS,
    MAX_TENTATIVAS,
    exigir_perfis,
    exigir_permissao,
    proteger_csrf,
    verificar_senha,
)
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import ip_cliente, registrar_auditoria_cursor
from backend.app.servicos.rtd_cliente import (
    MAX_ARQUIVO_ENVIO, ClienteRTD, ErroRTD, catalogar_documentos,
    protocolo_valido, hash_resumo,
)
from backend.app.servicos.rtd_uploads import ErroUploadRTD, MAX_UPLOAD_RTD, baixar_pdf_assinado
from backend.app.servicos.rtd_sincronizacao import TRAVA as TRAVA_SINCRONIZACAO_RTD

router = APIRouter(prefix='/api/rtd-intimacoes', tags=['RTD'], dependencies=[Depends(preparar_banco)])


class UploadRtdNovo(BaseModel):
    intimacao_id: UUID
    nome_arquivo: str = Field(min_length=1, max_length=120)
    tamanho: int = Field(gt=0, le=MAX_UPLOAD_RTD)


class UploadRtdOperacao(BaseModel):
    operacao: str


class ExclusaoProtocolosRtd(BaseModel):
    senha: str = Field(min_length=1, max_length=256)
    confirmacao: str = Field(min_length=1, max_length=20)


@router.post('/uploads', status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_upload_rtd(dados: UploadRtdNovo, request: Request,
                     usuario=Depends(exigir_permissao('alterar_intimacoes'))):
    if dados.nome_arquivo.casefold() != 'documentos rtd.pdf':
        raise HTTPException(422, 'Selecione o arquivo chamado exatamente “Documentos RTD.pdf”.')
    identificador = uuid4()
    pathname = f'rtd-intimacoes/temporarios/{identificador}.pdf'
    with conectar() as con, con.cursor() as cur:
        cur.execute('''SELECT protocolo,fase FROM intimacoes_aeri
            WHERE id=%s AND excluida_em IS NULL''', (dados.intimacao_id,))
        intimacao = cur.fetchone()
        if not intimacao:
            raise HTTPException(404, 'Intimação não encontrada ou está na lixeira.')
        if intimacao['fase'] != 'INTIMACAO':
            raise HTTPException(409, 'O envio de notificação está disponível apenas na fase inicial.')
        cur.execute('''UPDATE rtd_uploads_temporarios_aeri SET estado='EXPIRADO',alterado_em=NOW()
            WHERE estado IN ('AGUARDANDO_UPLOAD','PRONTO') AND expira_em<=NOW()''')
        cur.execute('''SELECT COUNT(*) AS total FROM rtd_uploads_temporarios_aeri
            WHERE usuario=%s AND estado IN ('AGUARDANDO_UPLOAD','PRONTO') AND expira_em>NOW()''', (usuario,))
        if cur.fetchone()['total'] >= 5:
            raise HTTPException(429, 'Há vários PDFs temporários pendentes. Feche envios anteriores e tente novamente.')
        cur.execute('''INSERT INTO rtd_uploads_temporarios_aeri
            (id,intimacao_id,usuario,pathname,nome_arquivo,tamanho_declarado)
            VALUES (%s,%s,%s,%s,%s,%s)''',
            (identificador, dados.intimacao_id, usuario, pathname, dados.nome_arquivo, dados.tamanho))
        registrar_auditoria_cursor(cur, request, 'rtd_upload_temporario_criado', 'sucesso', usuario,
                                   str(dados.intimacao_id), {'tamanho': dados.tamanho})
        con.commit()
    return {'upload_id': str(identificador), 'limite_bytes': MAX_UPLOAD_RTD}


@router.post('/uploads/{identificador}/autorizar', dependencies=[Depends(proteger_csrf)])
def autorizar_upload_rtd(identificador: UUID, dados: UploadRtdOperacao,
                         usuario=Depends(exigir_permissao('alterar_intimacoes'))):
    operacao = dados.operacao.strip().lower()
    if operacao not in {'put', 'get', 'delete'}:
        raise HTTPException(422, 'Operação de documento inválida.')
    with conectar() as con, con.cursor() as cur:
        cur.execute('''SELECT pathname,tamanho_declarado,estado,expira_em
            FROM rtd_uploads_temporarios_aeri
            WHERE id=%s AND usuario=%s''', (identificador, usuario))
        upload = cur.fetchone()
        if not upload:
            raise HTTPException(404, 'O envio temporário não foi encontrado.')
        expirou = upload['expira_em'] <= datetime.now(timezone.utc)
        if operacao == 'put' and (upload['estado'] != 'AGUARDANDO_UPLOAD' or expirou):
            raise HTTPException(409, 'Este envio temporário expirou. Selecione o PDF novamente.')
        if operacao == 'get' and (upload['estado'] not in {'AGUARDANDO_UPLOAD', 'PRONTO'} or expirou):
            raise HTTPException(409, 'Este PDF temporário já foi encerrado. Selecione-o novamente.')
        if operacao == 'delete' and upload['estado'] == 'EXCLUIDO':
            return {'pathname': upload['pathname'], 'tamanho': upload['tamanho_declarado'], 'removido': True}
        if operacao == 'delete':
            cur.execute('''UPDATE rtd_uploads_temporarios_aeri SET estado='EXPIRADO',alterado_em=NOW()
                WHERE id=%s AND usuario=%s''', (identificador, usuario))
        con.commit()
    return {'pathname': upload['pathname'], 'tamanho': upload['tamanho_declarado']}


@router.post('/uploads/{identificador}/remocao-confirmada', dependencies=[Depends(proteger_csrf)])
def confirmar_remocao_upload_rtd(identificador: UUID,
                                 usuario=Depends(exigir_permissao('alterar_intimacoes'))):
    with conectar() as con, con.cursor() as cur:
        cur.execute('''UPDATE rtd_uploads_temporarios_aeri SET estado='EXCLUIDO',alterado_em=NOW()
            WHERE id=%s AND usuario=%s''', (identificador, usuario))
        if cur.rowcount == 0:
            raise HTTPException(404, 'O envio temporário não foi encontrado.')
        con.commit()
    return {'ok': True}


@router.post('/uploads/limpar-metadados')
def limpar_metadados_uploads_rtd(request: Request):
    segredo = os.getenv('CRON_SECRET', '')
    recebido = request.headers.get('authorization', '').removeprefix('Bearer ').strip()
    if not segredo or not recebido or not hmac.compare_digest(recebido, segredo):
        raise HTTPException(401, 'Não autorizado.')
    with conectar() as con, con.cursor() as cur:
        cur.execute('''UPDATE rtd_uploads_temporarios_aeri SET estado='EXPIRADO',alterado_em=NOW()
            WHERE estado IN ('AGUARDANDO_UPLOAD','PRONTO') AND expira_em<=NOW()''')
        expirados = cur.rowcount
        cur.execute('''DELETE FROM rtd_uploads_temporarios_aeri
            WHERE expira_em<NOW()-INTERVAL '7 days' ''')
        removidos = cur.rowcount
        con.commit()
    return {'ok': True, 'expirados': expirados, 'metadadosRemovidos': removidos}


def _ambiente_envio_rtd():
    # Falha fechada: sem configuração explícita, nenhum envio pode alcançar produção.
    ambiente = os.getenv('AERI_RTD_NOTIFICACAO_AMBIENTE', 'homologacao').strip().lower()
    if ambiente not in ('producao', 'homologacao'):
        raise ErroRTD('RTD_CONFIG: ambiente de envio inválido.')
    return ambiente


def _consultar_documentos_pedido(protocolo):
    try:
        protocolo = protocolo_valido(protocolo)
    except ErroRTD as exc:
        raise HTTPException(422, str(exc)) from None

    with conectar() as con, con.cursor() as cur:
        cur.execute('''SELECT p.protocolo FROM rtd_pedidos_aeri p
            JOIN intimacoes_aeri i ON i.id=p.intimacao_id
            WHERE p.protocolo=%s AND i.excluida_em IS NULL''', (protocolo,))
        vinculo = cur.fetchone()
    if not vinculo:
        raise HTTPException(404, 'Pedido RTD não vinculado a uma intimação ativa do AERI.')

    try:
        cliente = ClienteRTD(ambiente='producao')
        pedido = cliente.pedido(protocolo)
        try:
            notas = cliente.notas_devolutivas(protocolo)
        except ErroRTD as exc:
            # Um protocolo pode ainda não ter nota devolutiva; mantém os demais anexos disponíveis.
            if 'RTD_HTTP_404' in str(exc):
                notas = []
            else:
                raise
        documentos = catalogar_documentos(protocolo, pedido, notas)
    except ErroRTD as exc:
        raise HTTPException(502, str(exc)) from None
    return cliente, documentos


@router.get('/{protocolo}/documentos')
def listar_documentos_rtd(protocolo: str, request: Request,
                          usuario=Depends(exigir_permissao('ver_intimacoes'))):
    _, documentos = _consultar_documentos_pedido(protocolo)
    with conectar() as con, con.cursor() as cur:
        registrar_auditoria_cursor(cur, request, 'rtd_documentos_consultados', 'sucesso', usuario,
                                   protocolo, {'quantidade': len(documentos)})
        con.commit()
    # As URLs da Central podem ser assinadas; nunca são expostas ao navegador.
    return {'protocolo': protocolo, 'documentos': [
        {'id': item['id'], 'titulo': item['titulo']} for item in documentos
    ]}


@router.get('/{protocolo}/documentos/{documento_id}')
def baixar_documento_rtd(protocolo: str, documento_id: str, request: Request,
                         usuario=Depends(exigir_permissao('ver_intimacoes'))):
    cliente, documentos = _consultar_documentos_pedido(protocolo)
    documento = next((item for item in documentos if item['id'] == documento_id), None)
    if not documento:
        raise HTTPException(404, 'O documento não está mais disponível na Central RTD.')

    try:
        arquivo = cliente.baixar_documento(documento['url'])
    except ErroRTD as exc:
        raise HTTPException(502, str(exc)) from None

    extensoes = {
        'application/pdf': '.pdf', 'image/jpeg': '.jpg', 'image/png': '.png',
        'image/tiff': '.tif', 'application/octet-stream': '.bin',
    }
    nome = arquivo['nome'] or f"RTD-{protocolo}-{documento_id}{extensoes[arquivo['tipo']]}"
    if '.' not in nome.rsplit('/', 1)[-1]:
        nome += extensoes[arquivo['tipo']]
    nome_ascii = ''.join(caractere if caractere.isascii() and (caractere.isalnum() or caractere in '._-') else '_'
                         for caractere in nome)[:140] or f'RTD-{protocolo}.bin'
    disposicao = f"attachment; filename=\"{nome_ascii}\"; filename*=UTF-8''{quote(nome, safe='')}"
    with conectar() as con, con.cursor() as cur:
        registrar_auditoria_cursor(cur, request, 'rtd_documento_baixado', 'sucesso', usuario,
                                   protocolo, {'documento': documento_id})
        con.commit()

    return StreamingResponse(iter((arquivo['conteudo'],)), media_type=arquivo['tipo'], headers={
        'Content-Disposition': disposicao,
        'Content-Length': str(len(arquivo['conteudo'])),
        'Cache-Control': 'private, no-store',
    })


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


@router.post('/intimacao/{identificador}/excluir-protocolos', dependencies=[Depends(proteger_csrf)])
def excluir_protocolos_rtd_intimacao(
    identificador: UUID,
    dados: ExclusaoProtocolosRtd,
    request: Request,
    usuario: str = Depends(exigir_perfis('ADMIN')),
):
    """Remove do AERI os protocolos RTD deste IN e registra uma supressÃ£o auditÃ¡vel.

    NÃ£o envia cancelamento Ã  Central RTD. As supressÃµes ficam no banco para
    impedir que a sincronizaÃ§Ã£o recrie protocolos que o cartÃ³rio removeu.
    """
    ip = ip_cliente(request)
    with conectar() as conexao, conexao.cursor() as cursor:
        # Serializa a exclusão com a sincronização. Sem a mesma trava, uma
        # consulta já em andamento poderia reinserir o protocolo após a limpeza.
        cursor.execute(
            'SELECT pg_try_advisory_xact_lock(%s) AS obteve',
            (TRAVA_SINCRONIZACAO_RTD,),
        )
        if not cursor.fetchone()['obteve']:
            registrar_auditoria_cursor(
                cursor, request, 'rtd_exclusao_protocolos', 'sincronizacao_em_andamento', usuario,
                str(identificador), {'motivo': 'trava_sincronizacao_ocupada'},
            )
            conexao.commit()
            raise HTTPException(
                409,
                'A sincronização RTD está em andamento. Aguarde alguns segundos e tente novamente.',
            )

        cursor.execute(
            """SELECT COUNT(*) AS total FROM auditoria_aeri
            WHERE acao='rtd_exclusao_senha' AND resultado='senha_invalida'
              AND usuario=%s AND ip=%s
              AND criada_em > NOW() - (%s * INTERVAL '1 minute')""",
            (usuario, ip, JANELA_TENTATIVAS_MINUTOS),
        )
        tentativas = int(cursor.fetchone()['total'])
        if tentativas >= MAX_TENTATIVAS:
            registrar_auditoria_cursor(
                cursor, request, 'rtd_exclusao_senha', 'bloqueado', usuario,
                str(identificador), {'motivo': 'limite_de_tentativas'},
            )
            conexao.commit()
            raise HTTPException(429, 'Muitas tentativas de senha. Aguarde 15 minutos e tente novamente.')

        cursor.execute(
            """SELECT senha_hash FROM usuarios_aeri
            WHERE usuario=%s AND perfil='ADMIN' AND ativo=TRUE FOR SHARE""",
            (usuario,),
        )
        conta = cursor.fetchone()
        if not conta or not verificar_senha(dados.senha, conta['senha_hash']):
            registrar_auditoria_cursor(
                cursor, request, 'rtd_exclusao_senha', 'senha_invalida', usuario,
                str(identificador), {'motivo': 'reautenticacao'},
            )
            conexao.commit()
            raise HTTPException(401, 'Senha incorreta. Nenhum protocolo RTD foi removido.')

        cursor.execute(
            """SELECT id,protocolo,protocolo_rtd
            FROM intimacoes_aeri WHERE id=%s FOR UPDATE""",
            (identificador,),
        )
        intimacao = cursor.fetchone()
        if not intimacao:
            raise HTTPException(404, 'IN nÃ£o encontrado.')
        if dados.confirmacao.strip().upper() != intimacao['protocolo'].upper():
            registrar_auditoria_cursor(
                cursor, request, 'rtd_exclusao_confirmacao', 'divergente', usuario,
                intimacao['protocolo'], {'motivo': 'protocolo_nao_confere'},
            )
            conexao.commit()
            raise HTTPException(422, 'O IN digitado nÃ£o confere. Nenhum protocolo RTD foi removido.')

        cursor.execute(
            """SELECT protocolo FROM rtd_pedidos_aeri
            WHERE in_documento=%s AND intimacao_id IS NOT NULL AND intimacao_id<>%s
            FOR UPDATE""",
            (intimacao['protocolo'], identificador),
        )
        conflitos_por_in = cursor.fetchall()
        if conflitos_por_in:
            registrar_auditoria_cursor(
                cursor, request, 'rtd_exclusao_protocolos', 'conflito_vinculo', usuario,
                intimacao['protocolo'], {'quantidade_conflitos': len(conflitos_por_in)},
            )
            conexao.commit()
            raise HTTPException(
                409,
                'HÃ¡ protocolo RTD do mesmo IN vinculado a outra intimaÃ§Ã£o. Corrija o vÃ­nculo antes de excluir.',
            )

        cursor.execute(
            """SELECT protocolo FROM rtd_pedidos_aeri
            WHERE intimacao_id=%s OR (intimacao_id IS NULL AND in_documento=%s)
            FOR UPDATE""",
            (identificador, intimacao['protocolo']),
        )
        pedidos = cursor.fetchall()
        protocolos_pedidos = {str(item['protocolo']) for item in pedidos}
        protocolos = set(protocolos_pedidos)

        cursor.execute(
            """SELECT id,protocolo FROM rtd_notificacao_envios_aeri
            WHERE intimacao_id=%s AND protocolo IS NOT NULL FOR UPDATE""",
            (identificador,),
        )
        envios = cursor.fetchall()
        protocolos.update(str(item['protocolo']) for item in envios if item.get('protocolo'))
        if intimacao.get('protocolo_rtd'):
            protocolos.add(str(intimacao['protocolo_rtd']))

        protocolos_validos = sorted(
            protocolo for protocolo in protocolos
            if re.fullmatch(r'[0-9]{17}', protocolo)
        )
        if protocolos_validos:
            cursor.execute(
                """SELECT protocolo FROM rtd_pedidos_aeri
                WHERE protocolo=ANY(%s) AND intimacao_id IS NOT NULL AND intimacao_id<>%s
                FOR UPDATE""",
                (protocolos_validos, identificador),
            )
            conflitos = cursor.fetchall()
            if conflitos:
                registrar_auditoria_cursor(
                    cursor, request, 'rtd_exclusao_protocolos', 'conflito_vinculo', usuario,
                    intimacao['protocolo'], {'quantidade_conflitos': len(conflitos)},
                )
                conexao.commit()
                raise HTTPException(
                    409,
                    'HÃ¡ protocolo RTD vinculado a outra intimaÃ§Ã£o. Corrija o vÃ­nculo antes de excluir.',
                )
        for protocolo in protocolos_validos:
            cursor.execute(
                """INSERT INTO rtd_protocolos_excluidos_aeri
                (protocolo,in_protocolo,excluido_por)
                VALUES (%s,%s,%s) ON CONFLICT(protocolo) DO NOTHING""",
                (protocolo, intimacao['protocolo'], usuario),
            )

        lista_protocolos_pedidos = sorted(protocolos_pedidos)
        if lista_protocolos_pedidos:
            cursor.execute(
                'DELETE FROM rtd_eventos_aeri WHERE protocolo=ANY(%s)',
                (lista_protocolos_pedidos,),
            )
            eventos_removidos = cursor.rowcount
            cursor.execute(
                'DELETE FROM rtd_leituras_aeri WHERE protocolo=ANY(%s)',
                (lista_protocolos_pedidos,),
            )
            leituras_removidas = cursor.rowcount
            cursor.execute(
                'DELETE FROM rtd_pedidos_aeri WHERE protocolo=ANY(%s)',
                (lista_protocolos_pedidos,),
            )
            pedidos_removidos = cursor.rowcount
        else:
            eventos_removidos = leituras_removidas = pedidos_removidos = 0

        if envios:
            cursor.execute(
                'DELETE FROM rtd_notificacao_envios_aeri WHERE intimacao_id=%s AND protocolo IS NOT NULL',
                (identificador,),
            )
            envios_removidos = cursor.rowcount
        else:
            envios_removidos = 0

        cursor.execute(
            """UPDATE intimacoes_aeri SET protocolo_rtd=NULL,atualizado_em=NOW()
            WHERE id=%s AND protocolo_rtd IS NOT NULL""",
            (identificador,),
        )
        campo_removido = cursor.rowcount > 0
        cursor.execute(
            """SELECT COUNT(*) AS total FROM rtd_notificacao_envios_aeri
            WHERE intimacao_id=%s AND protocolo IS NULL""",
            (identificador,),
        )
        tentativas_preservadas = int(cursor.fetchone()['total'])

        detalhes = {
            'pedidos_rtd': pedidos_removidos,
            'eventos_rtd': eventos_removidos,
            'leituras_rtd': leituras_removidas,
            'envios_com_protocolo': envios_removidos,
            'campo_legado_removido': campo_removido,
            'protocolos_suprimidos': len(protocolos_validos),
            'tentativas_sem_protocolo_preservadas': tentativas_preservadas,
        }
        registrar_auditoria_cursor(
            cursor, request, 'rtd_exclusao_protocolos', 'sucesso', usuario,
            intimacao['protocolo'], detalhes,
        )
        conexao.commit()

    return {'ok': True, **detalhes, 'jaEstavaLimpo': not any((
        pedidos_removidos, envios_removidos, campo_removido,
    ))}


class Leitura(BaseModel):
    versao: int = Field(ge=1)


class EnderecoNotificacao(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    cep: str = Field(alias='CEP', min_length=8, max_length=8)
    logradouro: str = Field(alias='Logradouro', min_length=2, max_length=160)
    numero: str = Field(alias='Numero', min_length=1, max_length=40)
    complemento: str = Field(default='', alias='Complemento', max_length=100)
    bairro: str = Field(alias='Bairro', min_length=2, max_length=100)
    cidade: str = Field(alias='Cidade', min_length=2, max_length=100)
    uf: str = Field(alias='UF', min_length=2, max_length=2)

    @field_validator('cep')
    @classmethod
    def validar_cep(cls, valor):
        if not valor.isdigit():
            raise ValueError('Informe um CEP com oito números.')
        return valor

    @field_validator('uf')
    @classmethod
    def normalizar_uf(cls, valor):
        valor = valor.strip().upper()
        if not re.fullmatch(r'[A-Z]{2}', valor):
            raise ValueError('Informe a sigla do estado.')
        return valor

    @field_validator('logradouro', 'numero', 'complemento', 'bairro', 'cidade', mode='before')
    @classmethod
    def limpar_texto(cls, valor):
        return str(valor or '').strip()

    def para_api(self):
        return {
            'CEP': int(self.cep), 'Logradouro': self.logradouro, 'Numero': self.numero,
            'Complemento': self.complemento, 'Bairro': self.bairro,
            'Cidade': self.cidade, 'UF': self.uf,
        }


class ParteNotificacao(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    nome: str = Field(alias='Nome', min_length=3, max_length=160)
    documento: str = Field(alias='CpfCnpj', min_length=11, max_length=14)
    endereco: EnderecoNotificacao = Field(alias='Endereco')

    @field_validator('nome', mode='before')
    @classmethod
    def limpar_nome(cls, valor):
        return str(valor or '').strip()

    @field_validator('documento', mode='before')
    @classmethod
    def normalizar_documento(cls, valor):
        return re.sub(r'\D', '', str(valor or ''))

    @field_validator('documento')
    @classmethod
    def validar_documento(cls, valor):
        if len(valor) not in (11, 14):
            raise ValueError('Informe um CPF com 11 números ou CNPJ com 14 números.')
        return valor

    def para_api(self, chave_documento='CpfCnpj'):
        return {'Nome': self.nome, chave_documento: self.documento,
                'Endereco': self.endereco.para_api()}


class RemetenteNotificacao(ParteNotificacao):
    documento: str = Field(alias='CPFCNPJ', min_length=11, max_length=14)


class PedidoNotificacao(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='forbid')
    remetente: RemetenteNotificacao = Field(alias='Remetente')
    cartorio_id: int = Field(alias='CartorioId', ge=1)
    cidade_destino: str = Field(alias='CidadeDestino', min_length=2, max_length=100)
    uf_destino: str = Field(alias='UFDestino', min_length=2, max_length=2)
    informacoes_adicionais: str = Field(default='', alias='InformacoesAdicionais', max_length=5000)
    entregue_somente_ao_destinatario: bool = Field(default=True, alias='EntregueSomenteAoDestinatario')
    notificados: list[ParteNotificacao] = Field(alias='Notificados', min_length=1, max_length=20)

    @field_validator('cidade_destino', 'informacoes_adicionais', mode='before')
    @classmethod
    def limpar_campos_texto(cls, valor):
        return str(valor or '').strip()

    @field_validator('informacoes_adicionais')
    @classmethod
    def validar_informacoes_adicionais(cls, valor):
        if not re.match(
                r'^Recebido em nome de: .{3,160}, inscrita no CNPJ: '
                r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\.(?:\s|$)', valor):
            raise ValueError('Informe o credor e seu CNPJ no campo de informações adicionais.')
        return valor

    @field_validator('uf_destino', mode='before')
    @classmethod
    def normalizar_uf_destino(cls, valor):
        return str(valor or '').strip().upper()

    @field_validator('uf_destino')
    @classmethod
    def validar_uf_destino(cls, valor):
        if not re.fullmatch(r'[A-Z]{2}', valor):
            raise ValueError('Informe a sigla do estado de destino.')
        return valor

    @field_validator('entregue_somente_ao_destinatario')
    @classmethod
    def validar_entrega(cls, valor):
        if valor is not True:
            raise ValueError('A notificação deve ser entregue somente ao destinatário ou representante legal.')
        return valor

    def para_api(self, arquivo_id):
        return {
            'Remetente': self.remetente.para_api('CPFCNPJ'),
            'CartorioId': self.cartorio_id,
            'ArquivoId': arquivo_id,
            'InformacoesAdicionais': self.informacoes_adicionais,
            'EntregueSomenteAoDestinatario': self.entregue_somente_ao_destinatario,
            'Notificados': [p.para_api() for p in self.notificados],
        }


def _resumo_envio(registro):
    return {
        'id': str(registro['id']), 'estado': registro['estado'],
        'protocolo': registro['protocolo'], 'cartorioId': registro['cartorio_id'],
        'ambiente': registro['ambiente'],
        'erro': registro['erro'], 'criadoEm': registro['criado_em'].isoformat(),
        'alteradoEm': registro['alterado_em'].isoformat(),
    }


@router.get('/cartorios')
def buscar_cartorios(uf: str, cidade: str,
                     _usuario=Depends(exigir_permissao('alterar_intimacoes'))):
    uf = uf.strip().upper()
    cidade = cidade.strip()
    if not re.fullmatch(r'[A-Z]{2}', uf) or len(cidade) < 2 or len(cidade) > 100:
        raise HTTPException(422, 'Informe o estado e a cidade de destino.')
    try:
        cliente = ClienteRTD(ambiente=_ambiente_envio_rtd())
        resultado = cliente.cartorios(uf, cidade)
    except ErroRTD as exc:
        raise HTTPException(502, str(exc)) from None
    return {'cartorios': resultado, 'ambiente': cliente.ambiente}


@router.get('/intimacao/{identificador}/envios')
def listar_envios(identificador: UUID,
                  _usuario=Depends(exigir_permissao('ver_intimacoes'))):
    with conectar() as con, con.cursor() as cur:
        # Uma execução interrompida não fica para sempre parecendo estar ativa.
        cur.execute('''UPDATE rtd_notificacao_envios_aeri SET estado='INCERTO',
            erro='A execução foi interrompida; confira na Central antes de tentar novamente.',
            alterado_em=NOW() WHERE intimacao_id=%s AND estado='ENVIANDO'
            AND alterado_em < NOW()-INTERVAL '5 minutes' ''', (identificador,))
        cur.execute('''SELECT id,chave_operacao,intimacao_id,usuario,estado,protocolo,
            cartorio_id,arquivo_id,ambiente,erro,criado_em,alterado_em
            FROM rtd_notificacao_envios_aeri WHERE intimacao_id=%s
            ORDER BY criado_em DESC LIMIT 20''', (identificador,))
        registros = cur.fetchall()
        con.commit()
    return {'envios': [_resumo_envio(item) for item in registros]}


@router.post('/notificacoes', status_code=201, dependencies=[Depends(proteger_csrf)])
async def enviar_notificacao_rtd(
    request: Request,
    usuario: str = Depends(exigir_permissao('alterar_intimacoes')),
):
    try:
        corpo = await request.json()
        id_intimacao = UUID(str(corpo.get('intimacao_id', '')))
        id_operacao = UUID(str(corpo.get('chave_operacao', '')))
        id_upload = UUID(str(corpo.get('upload_id', '')))
        url_assinada = str(corpo.get('url_assinada', ''))
        dados = PedidoNotificacao.model_validate(corpo.get('pedido'))
    except (ValueError, ValidationError, AttributeError):
        raise HTTPException(422, 'Revise os dados do remetente, destino e destinatários.') from None

    # A mesma chave pode ser reenviada após uma resposta perdida. Resolve a
    # idempotência antes de exigir novamente o arquivo temporário.
    with conectar() as con, con.cursor() as cur:
        cur.execute('''SELECT id,chave_operacao,intimacao_id,usuario,estado,protocolo,
            cartorio_id,ambiente,erro,criado_em,alterado_em FROM rtd_notificacao_envios_aeri
            WHERE chave_operacao=%s''', (id_operacao,))
        existente = cur.fetchone()
    if existente:
        if existente['estado'] in ('CRIADO', 'HOMOLOGACAO_OK'):
            return {'ok': True, 'repetido': True, **_resumo_envio(existente)}
        raise HTTPException(409, 'Este envio já está em processamento ou precisa ser conferido na Central.')

    with conectar() as con, con.cursor() as cur:
        cur.execute('''SELECT pathname,nome_arquivo,tamanho_declarado,estado
            FROM rtd_uploads_temporarios_aeri WHERE id=%s AND intimacao_id=%s AND usuario=%s
            AND estado IN ('AGUARDANDO_UPLOAD','PRONTO') AND expira_em>NOW()''',
            (id_upload, id_intimacao, usuario))
        upload = cur.fetchone()
    if not upload:
        raise HTTPException(409, 'O PDF temporário expirou ou não pertence a esta intimação. Selecione-o novamente.')
    nome_arquivo = upload['nome_arquivo']
    if nome_arquivo.casefold() != 'documentos rtd.pdf':
        raise HTTPException(422, 'O documento principal precisa ser “Documentos RTD.pdf”.')
    try:
        conteudo = baixar_pdf_assinado(url_assinada, upload['pathname'])
    except ErroUploadRTD as exc:
        raise HTTPException(422, str(exc)) from None
    if len(conteudo) != upload['tamanho_declarado'] or len(conteudo) > MAX_ARQUIVO_ENVIO:
        raise HTTPException(422, 'O PDF enviado não corresponde ao arquivo selecionado ou ultrapassa 25 MB.')
    with conectar() as con, con.cursor() as cur:
        cur.execute('''UPDATE rtd_uploads_temporarios_aeri SET estado='PRONTO',tamanho_verificado=%s,
            alterado_em=NOW() WHERE id=%s AND usuario=%s AND estado IN ('AGUARDANDO_UPLOAD','PRONTO')''',
            (len(conteudo), id_upload, usuario))
        con.commit()
    try:
        ambiente = _ambiente_envio_rtd()
    except ErroRTD as exc:
        raise HTTPException(500, str(exc)) from None

    # Persiste antes da chamada externa: queda do servidor não transforma um
    # envio potencialmente aceito em convite para repetir às cegas.
    registro_id = uuid4()
    try:
        with conectar() as con, con.cursor() as cur:
            cur.execute('SELECT protocolo,fase FROM intimacoes_aeri WHERE id=%s AND excluida_em IS NULL FOR UPDATE',
                        (id_intimacao,))
            intimacao = cur.fetchone()
            if not intimacao:
                raise HTTPException(404, 'A intimação não foi encontrada ou está na lixeira.')
            if intimacao['fase'] != 'INTIMACAO':
                raise HTTPException(409, 'A notificação só pode ser enviada para uma intimação da fase inicial.')
            cur.execute('''INSERT INTO rtd_notificacao_envios_aeri
                (id,chave_operacao,intimacao_id,usuario,estado,cartorio_id,ambiente)
                VALUES (%s,%s,%s,%s,'ENVIANDO',%s,%s)''',
                (registro_id, id_operacao, id_intimacao, usuario, dados.cartorio_id, ambiente))
            registrar_auditoria_cursor(cur, request, 'rtd_notificacao_envio_iniciado',
                'sucesso', usuario, str(id_intimacao), {'cartorio_id': dados.cartorio_id})
        con.commit()
    except UniqueViolation:
        with conectar() as con, con.cursor() as cur:
            cur.execute('''SELECT id,estado,protocolo,cartorio_id,ambiente,erro,criado_em,alterado_em
                FROM rtd_notificacao_envios_aeri WHERE chave_operacao=%s''', (id_operacao,))
            existente = cur.fetchone()
        if existente and existente['estado'] in ('CRIADO', 'HOMOLOGACAO_OK'):
            return {'ok': True, 'repetido': True, **_resumo_envio(existente)}
        raise HTTPException(409, 'Este envio já está em processamento ou precisa ser conferido na Central.') from None

    cliente = None
    try:
        cliente = ClienteRTD(ambiente=ambiente)
        cartorios = cliente.cartorios(dados.uf_destino, dados.cidade_destino)
        if not any(item['id'] == dados.cartorio_id for item in cartorios):
            raise HTTPException(422, 'O cartório selecionado não corresponde à cidade pesquisada. Busque novamente.')
    except HTTPException as exc:
        estado, mensagem = 'FALHA_VALIDACAO', str(exc.detail)
        with conectar() as con, con.cursor() as cur:
            cur.execute('''UPDATE rtd_notificacao_envios_aeri SET estado=%s,erro=%s,alterado_em=NOW()
                WHERE id=%s''', (estado, mensagem[:240], registro_id))
            registrar_auditoria_cursor(cur, request, 'rtd_notificacao_envio_validacao',
                'falha', usuario, str(id_intimacao), {'estado': estado})
        raise
    except ErroRTD as exc:
        estado = 'FALHA_VALIDACAO'
        with conectar() as con, con.cursor() as cur:
            cur.execute('''UPDATE rtd_notificacao_envios_aeri SET estado=%s,erro=%s,alterado_em=NOW()
                WHERE id=%s''', (estado, str(exc)[:240], registro_id))
            registrar_auditoria_cursor(cur, request, 'rtd_notificacao_envio_arquivo',
                'falha', usuario, str(id_intimacao), {'estado': estado})
        raise HTTPException(502, f'{exc} A notificação ainda não foi enviada.') from None

    try:
        arquivo_id = cliente.enviar_arquivo(nome_arquivo, conteudo)
    except ErroRTD as exc:
        estado = 'FALHA_ARQUIVO'
        with conectar() as con, con.cursor() as cur:
            cur.execute('''UPDATE rtd_notificacao_envios_aeri SET estado=%s,erro=%s,alterado_em=NOW()
                WHERE id=%s''', (estado, str(exc)[:240], registro_id))
            registrar_auditoria_cursor(cur, request, 'rtd_notificacao_envio_arquivo',
                'falha', usuario, str(id_intimacao), {'estado': estado})
        raise HTTPException(502, f'{exc} A notificação ainda não foi enviada.') from None

    with conectar() as con, con.cursor() as cur:
        cur.execute('''UPDATE rtd_notificacao_envios_aeri SET arquivo_id=%s,alterado_em=NOW()
            WHERE id=%s''', (arquivo_id, registro_id))
    con.commit()

    try:
        resposta = cliente.criar_notificacao(dados.para_api(arquivo_id))
    except ErroRTD as exc:
        estado = 'INCERTO' if exc.resultado_incerto else 'RECUSADO'
        with conectar() as con, con.cursor() as cur:
            cur.execute('''UPDATE rtd_notificacao_envios_aeri SET estado=%s,erro=%s,alterado_em=NOW()
                WHERE id=%s''', (estado, str(exc)[:240], registro_id))
            registrar_auditoria_cursor(cur, request, 'rtd_notificacao_envio',
                'incerto' if estado == 'INCERTO' else 'falha', usuario, str(id_intimacao), {'estado': estado})
        con.commit()
        if estado == 'INCERTO':
            raise HTTPException(502, 'A Central não confirmou se recebeu a notificação. Confira o histórico no RTD antes de tentar novamente.') from None
        raise HTTPException(502, 'A Central recusou a notificação. Revise os dados antes de tentar novamente.') from None

    protocolo = resposta['protocolo']
    estado = 'CRIADO'
    erro = None
    protocolo_confirmado = True
    try:
        protocolo_valido(protocolo)
    except ErroRTD:
        estado = 'CRIADO_REVISAR'
        protocolo_confirmado = False
        erro = 'A notificação foi criada, mas o protocolo retornado é inválido. Confira na Central antes de qualquer nova tentativa.'
    if ambiente == 'homologacao' and estado == 'CRIADO':
        estado = 'HOMOLOGACAO_OK'

    with conectar() as con, con.cursor() as cur:
        if protocolo_confirmado and ambiente == 'producao':
            cur.execute('SELECT intimacao_id FROM rtd_pedidos_aeri WHERE protocolo=%s FOR UPDATE', (protocolo,))
            vinculo_existente = cur.fetchone()
            if vinculo_existente and vinculo_existente['intimacao_id'] not in (None, id_intimacao):
                estado = 'CRIADO_REVISAR'
                erro = 'O protocolo já está vinculado a outra intimação; revise o vínculo manualmente.'
            elif vinculo_existente:
                cur.execute('''UPDATE rtd_pedidos_aeri SET intimacao_id=%s,vinculo='ENVIO_AERI',
                    pendente=TRUE,tentar_em=NOW(),erro=NULL,alterado_em=NOW()
                    WHERE protocolo=%s''', (id_intimacao, protocolo))
            else:
                dados_iniciais = {'Situacao': 'Enviado pelo AERI; aguardando consulta na Central'}
                cur.execute('''INSERT INTO rtd_pedidos_aeri
                    (protocolo,intimacao_id,vinculo,dados,resumo_hash,pendente,tentar_em)
                    VALUES (%s,%s,'ENVIO_AERI',%s,%s,TRUE,NOW())''',
                    (protocolo, id_intimacao, Jsonb(dados_iniciais), hash_resumo(dados_iniciais)))
        cur.execute('''UPDATE rtd_notificacao_envios_aeri SET estado=%s,protocolo=%s,erro=%s,
            alterado_em=NOW() WHERE id=%s RETURNING id,chave_operacao,intimacao_id,usuario,
            estado,protocolo,cartorio_id,arquivo_id,ambiente,erro,criado_em,alterado_em''',
            (estado, protocolo[:40], erro, registro_id))
        registro = cur.fetchone()
        registrar_auditoria_cursor(cur, request, 'rtd_notificacao_envio',
            'sucesso' if estado == 'CRIADO' else 'revisar', usuario, str(id_intimacao),
            {'estado': estado, 'protocolo': protocolo[:40], 'cartorio_id': dados.cartorio_id,
             'quantidade_destinatarios': len(dados.notificados)})
        con.commit()
    return {'ok': estado in ('CRIADO', 'HOMOLOGACAO_OK'), **_resumo_envio(registro)}


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
