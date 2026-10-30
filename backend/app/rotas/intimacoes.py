from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from backend.app.autenticacao import exigir_perfis, exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.servicos.intimacoes import (
    andamento_indica_intimacao_positiva,
    fase_por_andamento,
    intimacao_json,
    somar_dias_uteis,
    validar_campos_fase_inicial,
    validar_intimacao,
    validar_novo_andamento,
    validar_data_andamento,
)
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.rtd_sincronizacao import anexar_rtd
from backend.app.servicos.documentos_intimacao import (
    ErroDocumentoIntimacao,
    LIMITE_PDF_INTIMACAO,
    analisar_pdfs_intimacao,
    extrair_dados_documento_rtd,
)
from backend.app.servicos.contratos import cifrador, decifrar
from backend.app.servicos.preparacao_intimacao import complementar_tri7
from backend.app.servicos.rtd_uploads import ErroUploadRTD, baixar_pdf_assinado
from backend.app.servicos.anexos_intimacao import analisar_tres_anexos, VERSAO as FLUXO_DOCUMENTAL


router = APIRouter(
    prefix="/api/intimacoes",
    tags=["intimações"],
    dependencies=[Depends(preparar_banco)],
)


async def _json_documental(request: Request) -> dict:
    import json
    corpo = bytearray()
    async for parte in request.stream():
        if len(corpo) + len(parte) > 2048:
            raise HTTPException(413, 'Solicitação documental muito grande.')
        corpo.extend(parte)
    if not corpo:
        return {}
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'Envie a solicitação em JSON.')
    try:
        dados = json.loads(corpo)
        if not isinstance(dados, dict):
            raise ValueError()
        return dados
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, 'Solicitação documental inválida.') from None


def _analisar_versao_esperada(dados: dict) -> datetime:
    try:
        return datetime.fromisoformat(str(dados.get("atualizadoEm", "")))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Recarregue a lista antes de editar esta intimação."
        ) from exc


def _registrar_evento(cursor, identificador: UUID, protocolo: str, tipo: str, usuario: str, detalhes=None):
    cursor.execute(
        """INSERT INTO eventos_intimacao_aeri
        (intimacao_id, protocolo, tipo, usuario, detalhes)
        VALUES (%s, %s, %s, %s, %s)""",
        (identificador, protocolo, tipo, usuario, Jsonb(detalhes or {})),
    )


def _select_intimacoes() -> str:
    return """SELECT i.*,
        COALESCE((SELECT SUM(CASE WHEN l.tipo IN ('CREDITO','ESTORNO') THEN l.valor ELSE 0 END)
                  FROM lancamentos_intimacao_aeri l WHERE l.intimacao_id=i.id), i.valor_pago_onr) AS total_creditos,
        COALESCE((SELECT SUM(CASE WHEN l.tipo='REPASSE' THEN l.valor ELSE 0 END)
                  FROM lancamentos_intimacao_aeri l WHERE l.intimacao_id=i.id), i.valor_usado) AS total_repasses
        FROM intimacoes_aeri i"""


def _data_certificacao_cursor(cursor, data_intimacao: date | None, andamento: str) -> date | None:
    if not data_intimacao or not andamento_indica_intimacao_positiva(andamento):
        return None
    cursor.execute("SELECT data FROM feriados_aeri WHERE ativo=TRUE")
    return somar_dias_uteis(data_intimacao, 16, {item["data"] for item in cursor.fetchall()})


@router.post("/{identificador}/preparar-documentos-rede", dependencies=[Depends(proteger_csrf)], status_code=202)
async def solicitar_documentos_rede(identificador: UUID, request: Request,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes"))):
    import re
    from backend.app.servicos.contratos import cifrar
    try:
        opcoes = await _json_documental(request)
        if not isinstance(opcoes, dict):
            raise ValueError()
        if opcoes:
            if opcoes.get('fluxo') != FLUXO_DOCUMENTAL or opcoes.get('acao') not in {'listar', 'ler'}:
                raise ValueError()
            if opcoes.get('acao') == 'ler':
                selecao = opcoes.get('selecao', {})
                if set(selecao) != {'recibo', 'oficio', 'projecao'} or any(not re.fullmatch('[a-f0-9]{64}', str(v)) for v in selecao.values()):
                    raise ValueError()
                date.fromisoformat(opcoes['referencia'])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, 'Seleção de anexos ou data inválida.') from None
    try:
        cifrador()
    except RuntimeError:
        raise HTTPException(503, "Configure a chave de proteção no AERI e no executor para ler os documentos pela rede.") from None
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT fase FROM intimacoes_aeri WHERE id=%s AND excluida_em IS NULL FOR SHARE", (identificador,))
            item = cur.fetchone()
            if not item:
                raise HTTPException(404, "Intimação não encontrada.")
            if item['fase'] != 'INTIMACAO':
                raise HTTPException(409, "Preparação disponível apenas na fase inicial.")
            if opcoes:
                cur.execute("""UPDATE preparacoes_intimacao_aeri SET estado='ERRO', dados_cifrados=NULL,
                    erro='Leitura substituída por nova seleção.' WHERE intimacao_id=%s AND usuario=%s
                    AND estado IN ('PENDENTE','LENDO')""", (identificador, usuario))
            cur.execute("""UPDATE preparacoes_intimacao_aeri SET estado='ERRO', erro='A leitura expirou. Solicite novamente.'
                WHERE intimacao_id=%s AND usuario=%s AND estado IN ('PENDENTE','LENDO')
                AND atualizado_em < NOW() - INTERVAL '5 minutes'
                AND expira_em-criado_em > INTERVAL '20 minutes'""", (identificador, usuario))
            cur.execute("""INSERT INTO preparacoes_intimacao_aeri(id,intimacao_id,usuario,estado,dados_cifrados,expira_em)
                VALUES(%s,%s,%s,'PENDENTE',%s,NOW()+CASE WHEN %s THEN INTERVAL '15 minutes' ELSE INTERVAL '1 day' END) ON CONFLICT(intimacao_id,usuario)
                WHERE estado IN ('PENDENTE','LENDO') DO UPDATE SET usuario=EXCLUDED.usuario RETURNING id,estado""",
                (uuid4(), identificador, usuario, cifrar(opcoes) if opcoes else None, bool(opcoes)))
            trabalho = cur.fetchone()
            registrar_auditoria_cursor(cur, request, "solicitar_documentos_intimacao_rede", "sucesso", usuario, str(identificador), {})
        con.commit()
    return {"id": str(trabalho['id']), "estado": trabalho['estado']}


@router.get("/{identificador}/preparar-documentos-rede/{trabalho_id}")
def consultar_documentos_rede(identificador: UUID, trabalho_id: UUID, response: Response,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes"))):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("""SELECT p.estado,p.dados_cifrados,p.erro,u.nome AS nome_responsavel FROM preparacoes_intimacao_aeri p
                JOIN intimacoes_aeri i ON i.id=p.intimacao_id
                  LEFT JOIN usuarios_aeri u ON u.usuario=p.usuario
                WHERE p.id=%s AND p.intimacao_id=%s AND p.usuario=%s AND p.expira_em>NOW()
                AND i.excluida_em IS NULL AND i.fase='INTIMACAO'""", (trabalho_id, identificador, usuario))
            item = cur.fetchone()
    if not item:
        raise HTTPException(404, "Leitura não encontrada ou expirada.")
    dados = decifrar(item['dados_cifrados']) if item['estado'] == 'PRONTO' else None
    response.headers['Cache-Control'] = 'no-store'
    if dados and dados.get('fluxo') == FLUXO_DOCUMENTAL:
        # As credenciais Tri7 permanecem no backend; o executor só lê a pasta.
        from backend.app.servicos.enriquecimento_intimacao import complementar_preparacao
        complementar_preparacao(dados, item.get('nome_responsavel', ''))
    elif dados:
        # O executor tem acesso à unidade T:, mas a credencial Tri7 normalmente
        # fica apenas no servidor. Este complemento é somente leitura.
        dados['avisos'] = [aviso for aviso in dados['avisos']
            if not aviso.startswith('Não foi possível completar os dados pela Tri7.')]
        complementar_tri7(dados)
    return {"estado": item['estado'], "erro": item['erro'], "dados": dados}


@router.delete('/{identificador}/preparar-documentos-rede/{trabalho_id}', dependencies=[Depends(proteger_csrf)])
def descartar_leitura_documental(identificador: UUID, trabalho_id: UUID,
    usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('DELETE FROM preparacoes_intimacao_aeri WHERE id=%s AND intimacao_id=%s AND usuario=%s',
                        (trabalho_id, identificador, usuario))
        con.commit()
    return Response(status_code=204)


@router.post("/{identificador}/preparar-documentos", dependencies=[Depends(proteger_csrf)])
async def analisar_documentos_intimacao(
    identificador: UUID,
    request: Request,
    oficio: UploadFile = File(...),
    projecao: UploadFile = File(...),
    recibo: UploadFile = File(...),
    referencia: date | None = Form(None),
    titulo_registrado: UploadFile | None = File(None),
    usuario: str = Depends(exigir_permissao("alterar_intimacoes")),
):
    """Extrai dados dos três anexos obrigatórios; não os persiste nem envia."""
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT protocolo, protocolo_tri7, fase,
                    (SELECT nome FROM usuarios_aeri WHERE usuario=%s) AS nome_responsavel FROM intimacoes_aeri
                WHERE id=%s AND excluida_em IS NULL""",
                (usuario, identificador),
            )
            intimacao = cursor.fetchone()
    if not intimacao:
        raise HTTPException(status_code=404, detail="Intimação não encontrada ou está na lixeira.")
    if intimacao["fase"] != "INTIMACAO":
        raise HTTPException(status_code=409, detail="A preparação está disponível apenas na fase inicial da intimação.")

    oficio_bytes = await oficio.read(LIMITE_PDF_INTIMACAO + 1)
    projecao_bytes = await projecao.read(LIMITE_PDF_INTIMACAO + 1)
    recibo_bytes = await recibo.read(LIMITE_PDF_INTIMACAO + 1)
    for upload in (oficio, projecao, recibo, titulo_registrado):
        if upload:
            await upload.close()
    if sum(map(len, (oficio_bytes, projecao_bytes, recibo_bytes))) > 4_000_000:
        raise HTTPException(status_code=413, detail="Os três anexos passam de 4 MB no total. Utilize a leitura da pasta pelo executor, sem enviar os arquivos ao servidor.")
    try:
        from zoneinfo import ZoneInfo
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        resultado = analisar_tres_anexos(
            {'recibo': (recibo.filename, recibo_bytes), 'oficio': (oficio.filename, oficio_bytes),
             'projecao': (projecao.filename, projecao_bytes)},
            referencia or hoje, intimacao['protocolo'], intimacao['protocolo_tri7'] or '')
    except ErroDocumentoIntimacao as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    from backend.app.servicos.enriquecimento_intimacao import complementar_preparacao
    await run_in_threadpool(complementar_preparacao, resultado, intimacao.get('nome_responsavel', ''))

    # A auditoria registra apenas a operação e as contagens, nunca o texto dos PDFs.
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            registrar_auditoria_cursor(
                cursor,
                request,
                "preparar_documentos_intimacao",
                "sucesso",
                usuario,
                str(identificador),
                {
                    "devedores": len(resultado["devedores"]),
                    "enderecos": len(resultado["enderecos"]),
                    "avisos": len(resultado["avisos"]),
                },
            )
        conexao.commit()
    return resultado


@router.post('/{identificador}/documentos-evento', dependencies=[Depends(proteger_csrf)])
async def registrar_revisao_documental(identificador: UUID, request: Request,
    usuario: str = Depends(exigir_permissao('alterar_intimacoes'))):
    import re
    try:
        dados = await _json_documental(request)
        if dados.get('tipo') not in {'autuacao', 'oficio', 'convocacao'} or dados.get('acao') not in {'revisao', 'copia'}:
            raise ValueError()
        if dados.get('revisado') is not True or not re.fullmatch(r'INT/\d{4}/\d{3,6}', dados.get('numeroOficio', '')):
            raise ValueError()
        hashes = dados['fontes']
        if not isinstance(hashes, list) or len(hashes) != 3 or any(not isinstance(h, str) or not re.fullmatch('[a-f0-9]{64}', h) for h in hashes) or len(set(hashes)) != 3:
            raise ValueError()
        if not re.fullmatch('[a-f0-9]{64}', str(dados.get('rascunhoHash', ''))):
            raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(422, 'Confirme a revisão da versão atual e seus três anexos.') from None
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT id FROM intimacoes_aeri WHERE id=%s AND excluida_em IS NULL AND fase='INTIMACAO'", (identificador,))
            if not cur.fetchone():
                raise HTTPException(404, 'Intimação indisponível para preparar documentos.')
            cur.execute("""SELECT EXISTS(SELECT 1 FROM auditoria_aeri WHERE acao='copiar_documento_intimacao'
                AND recurso<>%s AND detalhes->>'numeroOficio'=%s) AS possivel_duplicidade""",
                (str(identificador), dados['numeroOficio']))
            duplicado = cur.fetchone()['possivel_duplicidade']
            if duplicado:
                raise HTTPException(409, 'Este número consta em uma cópia para outro IN no AERI. Confira a numeração oficial na Tri7 antes de continuar.')
            registrar_auditoria_cursor(cur, request,
                'revisar_documento_intimacao' if dados['acao'] == 'revisao' else 'copiar_documento_intimacao',
                'sucesso', usuario, str(identificador),
                {'tipo': dados['tipo'], 'numeroOficio': dados['numeroOficio'], 'fontes': hashes,
                 'rascunhoHash': dados['rascunhoHash'],
                 'numeroReservado': False, 'usoNaTri7Confirmado': False})
        con.commit()
    return {'registrado': True, 'numeroReservado': False}


@router.post("/{identificador}/extrair-documento-rtd", dependencies=[Depends(proteger_csrf)])
async def extrair_documento_rtd(
    identificador: UUID,
    request: Request,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes")),
):
    """Preenche o formulário a partir do PDF escolhido; não envia nada ao RTD."""
    try:
        corpo = await request.json()
        id_upload = UUID(str(corpo.get("upload_id", "")))
        url_assinada = str(corpo.get("url_assinada", ""))
    except (ValueError, AttributeError):
        raise HTTPException(422, "Selecione o PDF Documentos RTD.pdf novamente.") from None
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT protocolo FROM intimacoes_aeri WHERE id=%s AND excluida_em IS NULL", (identificador,))
            item = cursor.fetchone()
    if not item:
        raise HTTPException(404, "Intimação não encontrada ou está na lixeira.")
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""SELECT pathname,nome_arquivo,tamanho_declarado FROM rtd_uploads_temporarios_aeri
                WHERE id=%s AND intimacao_id=%s AND usuario=%s
                AND estado IN ('AGUARDANDO_UPLOAD','PRONTO') AND expira_em>NOW()""",
                (id_upload, identificador, usuario))
            upload = cursor.fetchone()
    if not upload:
        raise HTTPException(409, "O PDF temporário expirou ou não pertence a esta intimação. Selecione-o novamente.")
    if upload["nome_arquivo"].casefold() != "documentos rtd.pdf":
        raise HTTPException(422, "Selecione o arquivo Documentos RTD.pdf da pasta deste IN.")
    try:
        conteudo = baixar_pdf_assinado(url_assinada, upload["pathname"])
    except ErroUploadRTD as exc:
        raise HTTPException(422, str(exc)) from None
    if len(conteudo) != upload["tamanho_declarado"]:
        raise HTTPException(422, "O PDF recebido não corresponde ao arquivo selecionado. Selecione-o novamente.")
    try:
        dados = extrair_dados_documento_rtd(conteudo, item["protocolo"])
    except ErroDocumentoIntimacao as exc:
        raise HTTPException(422, str(exc)) from None
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("""UPDATE rtd_uploads_temporarios_aeri SET estado='PRONTO',tamanho_verificado=%s,
                alterado_em=NOW() WHERE id=%s AND usuario=%s AND estado IN ('AGUARDANDO_UPLOAD','PRONTO')""",
                (len(conteudo), id_upload, usuario))
            registrar_auditoria_cursor(cursor, request, "extrair_documento_rtd", "sucesso", usuario,
                str(identificador), {"devedores": len(dados["devedores"]), "enderecos": len(dados["enderecos"])})
        conexao.commit()
    return dados


@router.get("")
def listar_intimacoes(
    lixeira: bool = Query(False),
    _usuario: str = Depends(exigir_permissao("ver_intimacoes")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                _select_intimacoes() + (" WHERE i.excluida_em IS NOT NULL" if lixeira else " WHERE i.excluida_em IS NULL")
                + " ORDER BY i.protocolo"
            )
            return anexar_rtd(cursor, [intimacao_json(item) for item in cursor.fetchall()], _usuario)


@router.post("", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_intimacao(dados: dict, request: Request, usuario: str = Depends(exigir_permissao("criar_intimacoes"))):
    protocolo, credor, devedor, nome_andamento, andamento, fase = validar_intimacao(dados)
    campos = validar_campos_fase_inicial(dados)
    identificador = uuid4()
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                campos["data_certificacao"] = _data_certificacao_cursor(
                    cursor, campos["data_intimacao"], nome_andamento,
                ) or campos["data_certificacao"]
                cursor.execute(
                    """INSERT INTO intimacoes_aeri
                    (id, protocolo, credor, devedor, nome_andamento, ultimo_andamento, fase,
                    protocolo_rtd, numero_os_tri7, protocolo_tri7, certidao_decurso_prazo,
                    data_intimacao, data_certificacao, valor_pago_onr, valor_usado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *""",
                    (
                        identificador, protocolo, credor, devedor, nome_andamento, andamento, fase,
                        campos["protocolo_rtd"], campos["numero_os_tri7"], campos["protocolo_tri7"],
                        campos["certidao_decurso_prazo"], campos["data_intimacao"],
                        campos["data_certificacao"], campos["valor_pago_onr"], campos["valor_usado"],
                    ),
                )
                item = cursor.fetchone()
                _registrar_evento(cursor, identificador, protocolo, "CRIACAO", usuario, {"fase": fase})
                registrar_auditoria_cursor(
                    cursor, request, "criar_intimacao", "sucesso", usuario, protocolo)
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    return intimacao_json(item)


@router.put("/{identificador}", dependencies=[Depends(proteger_csrf)])
def atualizar_intimacao(identificador: UUID, dados: dict, request: Request, usuario: str = Depends(exigir_permissao("alterar_intimacoes"))):
    protocolo, credor, devedor, nome_andamento, andamento, fase = validar_intimacao(dados)
    campos = validar_campos_fase_inicial(dados)
    versao_esperada = _analisar_versao_esperada(dados)
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT * FROM intimacoes_aeri WHERE id=%s", (identificador,))
                anterior = cursor.fetchone()
                if not anterior:
                    raise HTTPException(status_code=404, detail="Intimação não encontrada.")
                campos["data_certificacao"] = _data_certificacao_cursor(
                    cursor, campos["data_intimacao"], nome_andamento,
                ) or campos["data_certificacao"]
                cursor.execute(
                    """UPDATE intimacoes_aeri SET protocolo=%s, credor=%s, devedor=%s,
                    nome_andamento=%s, ultimo_andamento=%s, fase=%s, protocolo_rtd=%s,
                    numero_os_tri7=%s, protocolo_tri7=%s, certidao_decurso_prazo=%s,
                    data_intimacao=%s, data_certificacao=%s, valor_pago_onr=%s,
                    valor_usado=%s, atualizado_em=NOW()
                    WHERE id=%s AND atualizado_em=%s RETURNING *""",
                    (
                        protocolo, credor, devedor, nome_andamento, andamento, fase,
                        campos["protocolo_rtd"], campos["numero_os_tri7"], campos["protocolo_tri7"],
                        campos["certidao_decurso_prazo"], campos["data_intimacao"],
                        campos["data_certificacao"], campos["valor_pago_onr"],
                        campos["valor_usado"], identificador, versao_esperada,
                    ),
                )
                item = cursor.fetchone()
                if not item:
                    # A trava otimista falhou: outra pessoa salvou uma
                    # alteração nesta intimação enquanto a tela estava aberta.
                    raise HTTPException(
                        status_code=409,
                        detail="Esta intimação foi alterada por outra pessoa. Recarregue e tente novamente.",
                    )
                campos_alterados = [
                    campo for campo, novo in {
                        "protocolo": protocolo,
                        "credor": credor,
                        "devedor": devedor,
                        "nome_andamento": nome_andamento,
                        "ultimo_andamento": andamento,
                        "fase": fase,
                        **campos,
                    }.items() if anterior.get(campo) != novo
                ]
                _registrar_evento(
                    cursor, identificador, protocolo, "ALTERACAO", usuario,
                    {"campos_alterados": campos_alterados, "fase": fase},
                )
                registrar_auditoria_cursor(
                    cursor, request, "atualizar_intimacao", "sucesso", usuario,
                    str(identificador))
            conexao.commit()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Este protocolo já está cadastrado.") from exc
    return intimacao_json(item)


@router.post("/{identificador}/conferir", dependencies=[Depends(proteger_csrf)])
def conferir_intimacao(
    identificador: UUID,
    request: Request,
    dados: dict | None = None,
    usuario: str = Depends(exigir_permissao("conferir_intimacoes")),
):
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    novo_andamento = validar_novo_andamento(dados)
    data_andamento = validar_data_andamento(dados, hoje)
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT historico, fase FROM intimacoes_aeri WHERE id=%s", (identificador,))
            atual = cursor.fetchone()
            if not atual:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            historico = list(dict.fromkeys([*(atual["historico"] or []), hoje]))
            if novo_andamento:
                fase = fase_por_andamento(novo_andamento, atual["fase"])
                cursor.execute(
                    """UPDATE intimacoes_aeri SET ultima_conferencia=%s, historico=%s,
                    nome_andamento=%s, ultimo_andamento=%s, fase=%s, atualizado_em=NOW()
                    WHERE id=%s RETURNING *""",
                    (hoje, Jsonb(historico), novo_andamento, data_andamento, fase, identificador),
                )
            else:
                cursor.execute(
                    """UPDATE intimacoes_aeri SET ultima_conferencia=%s, historico=%s,
                    atualizado_em=NOW() WHERE id=%s RETURNING *""",
                    (hoje, Jsonb(historico), identificador),
                )
            item = cursor.fetchone()
            _registrar_evento(
                cursor,
                identificador,
                item["protocolo"],
                "ANDAMENTO" if novo_andamento else "CONFERENCIA",
                usuario,
                {"houve_novo_andamento": bool(novo_andamento), "fase": item["fase"]},
            )
            registrar_auditoria_cursor(
                cursor, request, "conferir_intimacao", "sucesso", usuario,
                str(identificador))
        conexao.commit()
    return intimacao_json(item)


@router.delete("/{identificador}", status_code=204, dependencies=[Depends(proteger_csrf)])
def excluir_intimacao(identificador: UUID, request: Request, usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO"))):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT protocolo, fase, excluida_em FROM intimacoes_aeri WHERE id=%s", (identificador,))
            anterior = cursor.fetchone()
            if anterior and not anterior["excluida_em"]:
                _registrar_evento(
                    cursor, identificador, anterior["protocolo"], "EXCLUSAO", usuario,
                    {"fase": anterior["fase"]},
                )
            cursor.execute(
                "UPDATE intimacoes_aeri SET excluida_em=NOW(), excluida_por=%s, atualizado_em=NOW() "
                "WHERE id=%s AND excluida_em IS NULL", (usuario, identificador),
            )
            removidos = cursor.rowcount
            if removidos:
                registrar_auditoria_cursor(
                    cursor, request, "excluir_intimacao", "sucesso", usuario,
                    str(identificador))
        conexao.commit()
    if not removidos:
        raise HTTPException(status_code=404, detail="Intimação não encontrada.")
    return Response(status_code=204)


@router.post("/{identificador}/restaurar", dependencies=[Depends(proteger_csrf)])
def restaurar_intimacao(
    identificador: UUID, request: Request,
    usuario: str = Depends(exigir_perfis("ADMIN", "SUBSTITUTO")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE intimacoes_aeri SET excluida_em=NULL, excluida_por=NULL, atualizado_em=NOW() "
                "WHERE id=%s AND excluida_em IS NOT NULL RETURNING *", (identificador,),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Intimação não encontrada na lixeira.")
            _registrar_evento(cursor, identificador, item["protocolo"], "RESTAURACAO", usuario)
            registrar_auditoria_cursor(cursor, request, "restaurar_intimacao", "sucesso", usuario, str(identificador))
        conexao.commit()
    return intimacao_json(item)


@router.get("/{identificador}/financeiro")
def listar_financeiro(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("ver_intimacoes")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM lancamentos_intimacao_aeri WHERE intimacao_id=%s ORDER BY criado_em, id",
                (identificador,),
            )
            itens = cursor.fetchall()
    saldo = Decimal("0")
    retorno = []
    for item in itens:
        impacto = item["valor"] if item["tipo"] in {"CREDITO", "ESTORNO"} else -item["valor"]
        saldo += impacto
        retorno.append({
            "id": str(item["id"]), "tipo": item["tipo"], "valor": float(item["valor"]),
            "descricao": item["descricao"], "usuario": item["usuario"],
            "criadoEm": item["criado_em"].isoformat(), "saldoApos": float(saldo),
        })
    return {"itens": retorno, "saldo": float(saldo)}


@router.post("/{identificador}/financeiro", status_code=201, dependencies=[Depends(proteger_csrf)])
def criar_lancamento_financeiro(
    identificador: UUID, dados: dict, request: Request,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes")),
):
    tipo = str(dados.get("tipo") or "").upper()
    try:
        valor = Decimal(str(dados.get("valor"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Informe um valor válido.") from exc
    if tipo not in {"CREDITO", "REPASSE", "ESTORNO"} or valor <= 0:
        raise HTTPException(status_code=422, detail="Tipo ou valor do lançamento inválido.")
    descricao = str(dados.get("descricao") or "").strip()[:240] or None
    lancamento_id = uuid4()
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT protocolo FROM intimacoes_aeri WHERE id=%s AND excluida_em IS NULL", (identificador,))
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            cursor.execute(
                "INSERT INTO lancamentos_intimacao_aeri (id, intimacao_id, tipo, valor, descricao, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (lancamento_id, identificador, tipo, valor, descricao, usuario),
            )
            _registrar_evento(cursor, identificador, item["protocolo"], "LANCAMENTO_FINANCEIRO", usuario,
                              {"tipo": tipo, "valor": str(valor)})
            registrar_auditoria_cursor(cursor, request, "lancamento_financeiro_intimacao", "sucesso", usuario, str(identificador))
        conexao.commit()
    return {"id": str(lancamento_id), "ok": True}


@router.put("/{identificador}/checklist-desistencia", dependencies=[Depends(proteger_csrf)])
def atualizar_checklist_desistencia(
    identificador: UUID, dados: dict, request: Request,
    usuario: str = Depends(exigir_permissao("alterar_intimacoes")),
):
    permitidos = {"pedidoLocalizado", "documentosConferidos", "signatario", "notaGerada", "observacao"}
    checklist = {chave: dados[chave] for chave in permitidos if chave in dados}
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "UPDATE intimacoes_aeri SET checklist_desistencia=%s, atualizado_em=NOW() WHERE id=%s RETURNING protocolo",
                (Jsonb(checklist), identificador),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="Intimação não encontrada.")
            _registrar_evento(cursor, identificador, item["protocolo"], "CHECKLIST", usuario, {"campos": sorted(checklist)})
            registrar_auditoria_cursor(cursor, request, "checklist_desistencia", "sucesso", usuario, str(identificador))
        conexao.commit()
    return {"ok": True, "checklist": checklist}


@router.get("/{identificador}/historico")
def historico_intimacao(
    identificador: UUID,
    _usuario: str = Depends(exigir_permissao("ver_intimacoes")),
):
    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """SELECT id, protocolo, tipo, usuario, detalhes, criado_em
                FROM eventos_intimacao_aeri WHERE intimacao_id=%s
                ORDER BY criado_em DESC, id DESC LIMIT 500""",
                (identificador,),
            )
            return [
                {
                    "id": item["id"],
                    "protocolo": item["protocolo"],
                    "tipo": item["tipo"],
                    "usuario": item["usuario"],
                    "detalhes": item["detalhes"],
                    "criado_em": item["criado_em"].isoformat(),
                }
                for item in cursor.fetchall()
            ]
