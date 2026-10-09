import os
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.rtd_cliente import (
    MAX_ARQUIVO_ENVIO, ClienteRTD, ErroRTD, protocolo_valido, hash_resumo,
)

router = APIRouter(prefix='/api/rtd-intimacoes', tags=['RTD'], dependencies=[Depends(preparar_banco)])


def _ambiente_envio_rtd():
    # Falha fechada: sem configuração explícita, nenhum envio pode alcançar produção.
    ambiente = os.getenv('AERI_RTD_NOTIFICACAO_AMBIENTE', 'homologacao').strip().lower()
    if ambiente not in ('producao', 'homologacao'):
        raise ErroRTD('RTD_CONFIG: ambiente de envio inválido.')
    return ambiente


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
    intimacao_id: str = Form(...),
    chave_operacao: str = Form(...),
    pedido: str = Form(...),
    arquivo: UploadFile = File(...),
    usuario: str = Depends(exigir_permissao('alterar_intimacoes')),
):
    try:
        id_intimacao = UUID(intimacao_id)
        id_operacao = UUID(chave_operacao)
        dados = PedidoNotificacao.model_validate_json(pedido)
    except (ValueError, ValidationError):
        raise HTTPException(422, 'Revise os dados do remetente, destino e destinatários.') from None

    nome_arquivo = str(arquivo.filename or 'documento.pdf')
    if nome_arquivo.lower() != 'documentos rtd.pdf':
        raise HTTPException(422, 'O documento principal precisa ser “Documentos RTD.pdf”.')
    conteudo = await arquivo.read(MAX_ARQUIVO_ENVIO + 1)
    if not conteudo.startswith(b'%PDF') or len(conteudo) > MAX_ARQUIVO_ENVIO:
        raise HTTPException(422, 'Selecione um PDF válido, com até 4,3 MB.')
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
