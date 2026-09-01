import json
import hashlib
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation

from backend.app.autenticacao import exigir_permissao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.permissoes import selecionar_usuarios_com_permissoes
from backend.app.autenticacao import permissoes_sessao
from backend.app.seguranca_web import registrar_auditoria_cursor
from backend.app.servicos.tri7 import cliente_tri7, ClienteTri7, ErroTri7, normalizar_numero_matricula
from backend.app.servicos.contratos import (cifrador,cifrar,decifrar,documentos_publicos,
    extrair_contrato,confrontar,ficha_de,campos_ficha,servico,aplicar_decisoes,VERSAO_CONFRONTO,
    completar_juros_ausentes)
from backend.app.servicos.documentos_contratos import DocumentoInvalido, OcrIndisponivel, conferir_prazo

router=APIRouter(prefix="/api/contratos",tags=["contratos e minutas"],dependencies=[Depends(preparar_banco)])
acesso=exigir_permissao("acessar_contratos")


def numero(valor):
    try: return normalizar_numero_matricula(valor)
    except ValueError as exc: raise HTTPException(422,"Informe um número válido.") from exc


def _buscar(cursor, id, usuario, perfil, trava=False):
    cursor.execute("SELECT * FROM contratos_trabalhos_aeri WHERE id=%s"+(" FOR UPDATE" if trava else ""),(id,))
    r=cursor.fetchone()
    if not r or (r["usuario"]!=usuario and perfil not in {"ADMIN","SUBSTITUTO"}):
        raise HTTPException(404,"Trabalho não encontrado.")
    return r


def _publico(r):
    payload=decifrar(r["payload_cifrado"])
    if payload:
        payload.pop("documento",None) # Texto integral só no endpoint autenticado específico.
        if payload.get("confronto"):
            payload["confronto"].pop("texto",None)
    return {"id":str(r["id"]),"protocolo":r["protocolo"],"documentoId":r["documento_id"],
            "estado":r["estado"],"versao":r["versao"],"progresso":r["progresso"],"erro":r["erro"],"dados":payload,
            "confrontoAtual":payload.get('confronto',{}).get('versaoRegras')==VERSAO_CONFRONTO}


def _previa_minutas(ficha):
    """Monta a minuta logo na extracao, antes de qualquer confronto.

    E rascunho e vive em chave propria: `minutas` e o resultado conferido, que
    libera a copia e carrega as decisoes do conferente. Misturar os dois
    deixaria copiar para a Tri7 um texto que ninguem validou.
    """
    try:
        return servico.atos(ficha_de(ficha or {}))
    except Exception:
        # A previa e acessorio: ficha incompleta nao pode derrubar a extracao.
        return None


def _versao(r,dados):
    if dados.get("versao")!=r["versao"]:
        raise HTTPException(409,"Este trabalho mudou. Recarregue antes de salvar.")


def _salvar(cursor,r,payload,etapa,usuario,estado=None):
    versao=r["versao"]+1
    cifrado=cifrar(payload)
    cursor.execute("""UPDATE contratos_trabalhos_aeri SET payload_cifrado=%s,versao=%s,estado=%s,atualizado_em=NOW()
        WHERE id=%s RETURNING *""",(cifrado,versao,estado or r["estado"],r["id"]))
    salvo=cursor.fetchone()
    cursor.execute("INSERT INTO contratos_versoes_aeri(trabalho_id,versao,usuario,etapa,payload_cifrado) VALUES(%s,%s,%s,%s,%s)",
                   (r["id"],versao,usuario,etapa,cifrado))
    return salvo


@router.get("/protocolo/{protocolo}")
def consultar_protocolo(protocolo:str,_usuario=Depends(acesso)):
    try:
        r=cliente_tri7().listar_documentos_protocolo(numero(protocolo))
        return {"protocolo":numero(protocolo),"titulo":r["protocolo"].get("descricao_titulo"),
                "documentos":documentos_publicos(r["documentos"]),
                "mensagem":"Selecione o contrato. A seleção explícita evita confundir versões, validações ou anexos."}
    except ErroTri7 as exc: raise HTTPException(502,str(exc)) from exc


@router.post("",dependencies=[Depends(proteger_csrf)],status_code=202)
def iniciar(dados:dict,request:Request,usuario=Depends(acesso)):
    protocolo,doc=numero(dados.get("protocolo")),numero(dados.get("documentoId"))
    try:
        cifrador() # Não enfileira documentação sem proteção configurada.
        r=cliente_tri7().listar_documentos_protocolo(protocolo)
    except ErroTri7 as exc: raise HTTPException(502,str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
    if doc not in {str(d.get("ged_documento_id")) for d in r["documentos"]}:
        raise HTTPException(422,"O documento selecionado não pertence ao protocolo consultado.")
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT usuario FROM usuarios_aeri WHERE usuario=%s FOR UPDATE",(usuario,))
            # Retomar antes de contar: cinco pendentes não podem bloquear sua própria retomada.
            cur.execute("""SELECT * FROM contratos_trabalhos_aeri WHERE usuario=%s AND protocolo=%s
                AND documento_id=%s AND estado IN ('AGUARDANDO','PROCESSANDO') FOR UPDATE""",(usuario,protocolo,doc))
            existente=cur.fetchone()
            if existente:
                return _publico(existente)
            cur.execute("SELECT COUNT(*) AS n FROM contratos_trabalhos_aeri WHERE usuario=%s AND estado IN ('AGUARDANDO','PROCESSANDO')",(usuario,))
            if cur.fetchone()["n"]>=5: raise HTTPException(429,"Aguarde os trabalhos em andamento antes de solicitar outro.")
            cur.execute("""INSERT INTO contratos_trabalhos_aeri(id,usuario,protocolo,documento_id)
            VALUES(%s,%s,%s,%s) ON CONFLICT (usuario,protocolo,documento_id)
            WHERE estado IN ('AGUARDANDO','PROCESSANDO') DO UPDATE SET atualizado_em=contratos_trabalhos_aeri.atualizado_em RETURNING *""",
            (uuid4(),usuario,protocolo,doc))
            trabalho=cur.fetchone()
            registrar_auditoria_cursor(cur,request,"contrato_enfileirado","sucesso",usuario,str(trabalho["id"]),{"protocolo":protocolo,"documento":doc})
        con.commit()
    return _publico(trabalho)


@router.post("/{id}/extrair",dependencies=[Depends(proteger_csrf)])
def extrair_agora(id:UUID,request:Request,usuario=Depends(acesso)):
    """Processa apenas o trabalho escolhido na própria requisição, nunca a fila inteira."""
    try:
        cifrador()
        # Cliente com limites próprios; não muda timeout/token dos outros módulos.
        config=replace(cliente_tri7().configuracao,timeout=8,tentativas_transitorias=1)
        cli=ClienteTri7(config)
    except ErroTri7 as exc: raise HTTPException(502,str(exc)) from exc
    except RuntimeError as exc: raise HTTPException(503,str(exc)) from exc
    token=uuid4()
    with conectar() as con:
        with con.cursor() as cur:
            r=_buscar(cur,id,usuario,request.state.sessao['perfil'],True)
            if r['estado'] in {'EXTRAIDO','CONFERIDO','MINUTA'}:
                return _publico(r) # Não sobrescrever ficha/decisões já conferidas.
            if r['trava_ate'] and r['trava_ate']>datetime.now(timezone.utc):
                return _publico(r) # Requisição concorrente não inicia outra extração.
            cur.execute("""UPDATE contratos_trabalhos_aeri SET estado='PROCESSANDO',erro=NULL,
                progresso=0,trava=%s,trava_ate=NOW()+INTERVAL '90 seconds',atualizado_em=NOW()
                WHERE id=%s""",(token,id))
            registrar_auditoria_cursor(cur,request,"contrato_extracao_direta","iniciado",usuario,str(id))
        con.commit()
    _processar_contrato_reservado(r,token,cli=cli,permitir_ocr=False,prazo=time.monotonic()+45)
    with conectar() as con:
        with con.cursor() as cur:
            return _publico(_buscar(cur,id,usuario,request.state.sessao['perfil']))


@router.get("")
def listar(usuario=Depends(acesso)):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT id,protocolo,estado,progresso,criado_em FROM contratos_trabalhos_aeri WHERE usuario=%s ORDER BY criado_em DESC LIMIT 30",(usuario,))
            return [{**r,"id":str(r["id"])} for r in cur.fetchall()]


@router.get("/{id}")
def obter(id:UUID,request:Request,usuario=Depends(acesso)):
    with conectar() as con:
        with con.cursor() as cur: return _publico(_buscar(cur,id,usuario,request.state.sessao["perfil"]))


@router.get("/{id}/texto")
def texto_extraido(id:UUID,request:Request,usuario=Depends(acesso)):
    with conectar() as con:
        with con.cursor() as cur: r=_buscar(cur,id,usuario,request.state.sessao["perfil"])
    p=decifrar(r["payload_cifrado"])
    return p.get("documento",{})


@router.get("/{id}/documento")
def documento(id:UUID,request:Request,usuario=Depends(acesso)):
    with conectar() as con:
        with con.cursor() as cur: r=_buscar(cur,id,usuario,request.state.sessao["perfil"])
    try:
        cli=cliente_tri7()
        docs=cli.listar_documentos_protocolo(r["protocolo"])["documentos"]
        if r["documento_id"] not in {str(d.get("ged_documento_id")) for d in docs}:
            raise HTTPException(404,"Documento não está mais vinculado ao protocolo.")
        arquivo=cli.buscar_documento_ged(r["documento_id"])
        armazenado=decifrar(r["payload_cifrado"]).get("documento",{}).get("sha256")
        if armazenado and hashlib.sha256(arquivo["dados"]).hexdigest()!=armazenado:
            raise HTTPException(409,"O documento GED mudou desde a extração. Inicie novo trabalho para conferir a versão atual.")
        tipo=arquivo.get("content_type","").split(';')[0].lower()
        extensao={"application/pdf":"pdf","image/png":"png","image/jpeg":"jpg","image/tiff":"tif"}.get(tipo,"bin")
        return Response(arquivo["dados"],media_type=tipo if extensao!="bin" else "application/octet-stream",headers={"Content-Disposition":f'attachment; filename="GED-{r["documento_id"]}.{extensao}"',"Cache-Control":"no-store"})
    except ErroTri7 as exc: raise HTTPException(502,str(exc)) from exc


@router.post("/{id}/matricula",dependencies=[Depends(proteger_csrf)])
def comparar(id:UUID,dados:dict,request:Request,usuario=Depends(acesso)):
    if len(json.dumps(dados))>1_000_000: raise HTTPException(413,"Ficha muito grande.")
    with conectar() as con:
        with con.cursor() as cur: r=_buscar(cur,id,usuario,request.state.sessao["perfil"])
    _versao(r,dados)
    if r["estado"] not in {"EXTRAIDO","CONFERIDO","MINUTA"}: raise HTTPException(409,"Aguarde a extração do contrato.")
    p=decifrar(r["payload_cifrado"])
    try:
        editada=servico.para_json(ficha_de(dados.get("ficha",p["ficha"])))
        # Metadados de extração não são sobrescritos pelo navegador.
        editada["origens"]=p["ficha"]["origens"]; editada["brutos"]=p["ficha"]["brutos"]
        p["ficha"]=editada
        completar_juros_ausentes(p)
        # A previa acompanha o que o conferente editou na ficha.
        p["minutasPrevia"]=_previa_minutas(p["ficha"])
    except (ValueError,TypeError,KeyError) as exc: raise HTTPException(422,"Ficha inválida.") from exc
    n=numero(dados.get("matricula"))
    try:
        texto=cliente_tri7().buscar_texto_matricula(n)["texto"]
        # Mesmas regras aprovadas que a consulta oficial, sem dados cadastrais.
        from backend.app.rotas.analisador import _regras_aprovadas
        p["confronto"]=confrontar(p,texto,n,_regras_aprovadas())
        p.pop("decisoes",None); p.pop("minutas",None); p.pop("minutasFinais",None)
    except ErroTri7 as exc: raise HTTPException(502,str(exc)) from exc
    with conectar() as con:
        with con.cursor() as cur:
            atual=_buscar(cur,id,usuario,request.state.sessao["perfil"],True); _versao(atual,dados)
            salvo=_salvar(cur,atual,p,"CONFRONTO",usuario,"CONFERIDO")
            registrar_auditoria_cursor(cur,request,"contrato_confrontado","sucesso",usuario,str(id),{"matricula":n})
        con.commit()
    return _publico(salvo)


@router.post("/{id}/previa",dependencies=[Depends(proteger_csrf)])
def previa(id:UUID,dados:dict,request:Request,usuario=Depends(acesso)):
    """Remonta o rascunho da minuta enquanto o conferente digita.

    Nao grava nada: nao salva payload, nao mexe na versao e nao vira `minutas`.
    Serve so para a coluna ao lado da ficha acompanhar a edicao. A checagem de
    acesso continua valendo -- ficha de contrato nao e publica.
    """
    if len(json.dumps(dados))>1_000_000: raise HTTPException(413,"Ficha muito grande.")
    ficha=dados.get("ficha")
    if not isinstance(ficha,dict): raise HTTPException(422,"Ficha invalida.")
    with conectar() as con:
        with con.cursor() as cur:
            _buscar(cur,id,usuario,request.state.sessao["perfil"])
    return {"minutasPrevia":_previa_minutas(ficha)}


@router.post("/{id}/gerar",dependencies=[Depends(proteger_csrf)])
def gerar(id:UUID,dados:dict,request:Request,usuario=Depends(acesso)):
    if len(json.dumps(dados))>1_000_000: raise HTTPException(413,"Ficha muito grande.")
    with conectar() as con:
        with con.cursor() as cur:
            r=_buscar(cur,id,usuario,request.state.sessao["perfil"],True); _versao(r,dados)
            p=decifrar(r["payload_cifrado"])
            if not p.get("confronto"): raise HTTPException(409,"Consulte a matrícula e confira os dados antes de gerar.")
            if p['confronto'].get('versaoRegras') != VERSAO_CONFRONTO:
                raise HTTPException(409,"A conferência foi feita com regras anteriores. Clique em Confrontar com a matrícula novamente.")
            decisoes=dados.get("decisoes") or {}
            ficha=dados.get("ficha")
            if not isinstance(ficha,dict): raise HTTPException(422,"Ficha inválida.")
            try:
                nova,aplicadas=aplicar_decisoes(p,ficha,decisoes,dados.get("extracaoConferida"))
                reconstruida=ficha_de(nova)
                minutas=servico.atos(reconstruida)
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
            except (TypeError,ValueError,AttributeError,KeyError) as exc:
                raise HTTPException(422,"Revise os campos e valores da ficha.") from exc
            anteriores={c["campo"]:c["valor"] for c in campos_ficha(p["fichaOriginal"])}
            # Complemento automatico do B9 nao e apresentado como edicao humana.
            anteriores.update({c:d["valor"] for c,d in p.get("complementosExtracao",{}).items()})
            alteracoes=[{"campo":c["campo"],"antes":anteriores.get(c["campo"]),"depois":c["valor"],"origem":"HUMANA"}
                        for c in campos_ficha(nova) if c["valor"]!=anteriores.get(c["campo"])]
            # Contrato, matrícula e decisões permanecem lado a lado, sem sobrescrever a extração original.
            p.update(fichaGerada=nova,decisoes=aplicadas,alteracoesHumanas=alteracoes,minutas=minutas)
            p.pop("minutasFinais",None)
            salvo=_salvar(cur,r,p,"GERACAO_CONFERIDA",usuario,"MINUTA")
            registrar_auditoria_cursor(cur,request,"minuta_gerada","sucesso",usuario,str(id),{"alteracoes":len(alteracoes)})
        con.commit()
    return _publico(salvo)


@router.put("/{id}/minuta",dependencies=[Depends(proteger_csrf)])
def editar_minuta(id:UUID,dados:dict,request:Request,usuario=Depends(acesso)):
    final=dados.get("textos") or {}
    if set(final)!={"venda","alienacao"} or any(not isinstance(v,str) or len(v)>100_000 for v in final.values()):
        raise HTTPException(422,"Textos da minuta inválidos.")
    with conectar() as con:
        with con.cursor() as cur:
            r=_buscar(cur,id,usuario,request.state.sessao["perfil"],True); _versao(r,dados)
            p=decifrar(r["payload_cifrado"])
            if not p.get("minutas"): raise HTTPException(409,"Gere a minuta antes de editar.")
            p["minutasFinais"]=final
            salvo=_salvar(cur,r,p,"EDICAO_HUMANA",usuario,"MINUTA")
            registrar_auditoria_cursor(cur,request,"minuta_editada","sucesso",usuario,str(id))
        con.commit()
    return _publico(salvo)


@router.get("/{id}/historico")
def historico(id:UUID,request:Request,usuario=Depends(acesso)):
    with conectar() as con:
        with con.cursor() as cur:
            _buscar(cur,id,usuario,request.state.sessao["perfil"])
            cur.execute("SELECT versao,usuario,etapa,criado_em FROM contratos_versoes_aeri WHERE trabalho_id=%s ORDER BY versao",(id,))
            return cur.fetchall()


def processar_proximo_contrato():
    token=uuid4()
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("""SELECT * FROM contratos_trabalhos_aeri WHERE estado='AGUARDANDO'
                OR (estado='PROCESSANDO' AND trava_ate<NOW()) ORDER BY criado_em FOR UPDATE SKIP LOCKED LIMIT 1""")
            r=cur.fetchone()
            if not r: return {"estado":"SEM_TRABALHO"}
            cur.execute(selecionar_usuarios_com_permissoes("WHERE u.usuario=%s",ordem=""),(r["usuario"],))
            u=cur.fetchone()
            if not u or not u["ativo"] or not permissoes_sessao(u).get("acessar_contratos"):
                cur.execute("UPDATE contratos_trabalhos_aeri SET estado='FALHA',erro='Acesso do solicitante revogado.' WHERE id=%s",(r["id"],))
                con.commit(); return {"estado":"ACESSO_REVOGADO"}
            cur.execute("UPDATE contratos_trabalhos_aeri SET estado='PROCESSANDO',trava=%s,trava_ate=NOW()+INTERVAL '15 minutes' WHERE id=%s",(token,r["id"]))
        con.commit()
    return _processar_contrato_reservado(r,token)


def _processar_contrato_reservado(r,token,*,cli=None,permitir_ocr=True,prazo=None):
    ultima_atualizacao=0.0
    def progresso(feitas,total):
        nonlocal ultima_atualizacao
        conferir_prazo(prazo)
        # PDF digital é rápido: não abrir uma conexão ao banco para cada página.
        agora=time.monotonic()
        if feitas != total and agora-ultima_atualizacao<2:
            return
        ultima_atualizacao=agora
        with conectar() as con:
            with con.cursor() as cur:
                cur.execute("UPDATE contratos_trabalhos_aeri SET progresso=%s,atualizado_em=NOW() WHERE id=%s AND trava=%s",
                            (round(feitas/total*100),r["id"],token))
                if not cur.rowcount: raise RuntimeError("Lease perdido.")
                if permitir_ocr:
                    cur.execute("UPDATE contratos_trabalhos_aeri SET trava_ate=NOW()+INTERVAL '15 minutes' WHERE id=%s AND trava=%s",(r["id"],token))
            con.commit()
    erro=None; p=None
    try:
        cli=cli or cliente_tri7()
        conferir_prazo(prazo)
        docs=cli.listar_documentos_protocolo(r["protocolo"])["documentos"]
        if r["documento_id"] not in {str(d.get("ged_documento_id")) for d in docs}:
            raise ValueError("O documento não pertence mais ao protocolo.")
        conferir_prazo(prazo)
        arquivo=cli.buscar_documento_ged(r["documento_id"])
        conferir_prazo(prazo)
        p=extrair_contrato(arquivo["dados"],progresso,permitir_ocr=permitir_ocr,prazo=prazo)
        p["minutasPrevia"]=_previa_minutas(p.get("ficha"))
        p["origemGed"]={"protocolo":r["protocolo"],"documentoId":r["documento_id"],"metadados":next(d for d in documentos_publicos(docs) if str(d["ged_documento_id"])==r["documento_id"])}
    except (OcrIndisponivel,DocumentoInvalido,ValueError) as exc: erro=str(exc)[:250]
    except ErroTri7 as exc: erro=str(exc)[:250]
    except Exception as exc: erro=f"Falha controlada na extração ({type(exc).__name__}). Tente novamente ou contate o suporte."
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM contratos_trabalhos_aeri WHERE id=%s AND trava=%s FOR UPDATE",(r["id"],token))
            atual=cur.fetchone()
            if not atual: return {"estado":"LEASE_PERDIDO"}
            if erro:
                cur.execute("UPDATE contratos_trabalhos_aeri SET estado='FALHA',erro=%s,trava=NULL,trava_ate=NULL,atualizado_em=NOW() WHERE id=%s",(erro,r["id"]))
            else:
                _salvar(cur,atual,p,"EXTRACAO",r["usuario"],"EXTRAIDO")
                cur.execute("UPDATE contratos_trabalhos_aeri SET progresso=100,trava=NULL,trava_ate=NULL WHERE id=%s",(r["id"],))
        con.commit()
    return {"id":str(r["id"]),"estado":"FALHA" if erro else "EXTRAIDO"}
