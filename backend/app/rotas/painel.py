import hmac
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from psycopg.types.json import Jsonb

from backend.app.autenticacao import usuario_atual, exigir_permissao, permissoes_sessao, proteger_csrf
from backend.app.database import conectar, preparar_banco
from backend.app.servicos.painel import modulos_permitidos
from backend.app.servicos.automacoes_operacionais import pendencias_intimacoes, executar_passo
from backend.app.seguranca_web import registrar_auditoria_cursor

router = APIRouter(prefix="/api", tags=["painéis"], dependencies=[Depends(preparar_banco)])


@router.get("/painel")
def painel(request: Request, _usuario=Depends(usuario_atual)):
    if request.state.sessao["deve_trocar_senha"]:
        raise HTTPException(403, "Troque sua senha temporária para continuar.")
    permissoes = permissoes_sessao(request.state.sessao)
    alertas = []
    with conectar() as con:
        with con.cursor() as cur:
            if permissoes.get("acessar_livro_protocolos"):
                cur.execute("SELECT estado,ocorrencias,protocolos,fim,inicio,erro FROM execucoes_operacionais_aeri WHERE chave='livro_protocolos' ORDER BY inicio DESC LIMIT 1")
                item = cur.fetchone()
                total = item["ocorrencias"] if item else 0
                mensagem = (f"{total} ocorrências encontradas" if total else "Sem ocorrências nesta verificação") if item else "Verificação automática ainda não executada"
                if item and item["estado"] != "CONCLUIDO":
                    mensagem = f"Verificação {item['estado'].lower()}: {item['protocolos']} protocolos, {total} ocorrências. Resultado ainda não conclusivo."
                alertas.append(dict(modulo="livroproto", titulo="Livro de Protocolos", total=total, mensagem=mensagem,estado=item['estado'] if item else 'AGUARDANDO',
                                    atualizadoEm=(item["fim"] or item["inicio"]).isoformat() if item else None))
            if permissoes.get("ver_intimacoes"):
                pendentes = pendencias_intimacoes(cur)
                alertas.append(dict(modulo="rotina", titulo="Intimações", total=len(pendentes),
                    mensagem=f"{len(pendentes)} intimações pendentes, atrasadas ou sem atividade de conferência",
                    atualizadoEm=datetime.now(timezone.utc).isoformat()))
    return {"modulos": modulos_permitidos(permissoes), "alertas": alertas}


class ConfiguracaoAgenda(BaseModel):
    habilitada: bool
    intervalo_minutos: int = Field(ge=15, le=1440)
    hora_inicio: int = Field(ge=0, le=23)
    hora_fim: int = Field(ge=1, le=24)
    dias_semana: list[int] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def horario(self):
        if self.hora_fim <= self.hora_inicio or any(d not in range(7) for d in self.dias_semana):
            raise ValueError("Horário ou dias inválidos.")
        return self


@router.get("/sistema/configuracao")
def configuracao(_usuario=Depends(exigir_permissao("configurar_sistema"))):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT chave,habilitada,intervalo_minutos,hora_inicio,hora_fim,dias_semana,ultima_tentativa,ultimo_sucesso,proxima_execucao FROM automacoes_operacionais_aeri ORDER BY chave")
            agendas = cur.fetchall()
            cur.execute("SELECT id,chave,estado,inicio,fim,duracao_ms,protocolos,ocorrencias,erro FROM execucoes_operacionais_aeri ORDER BY inicio DESC LIMIT 20")
            execucoes = cur.fetchall()
    return {"agendas": agendas, "execucoes": execucoes, "oficio": {"webhookConfigurado": bool(os.getenv("ONR_WEBHOOK_SECRET"))},
            "executor": "Worker operacional independente do navegador; precisa estar instalado e em execução."}


@router.put("/sistema/agendas/{chave}", dependencies=[Depends(proteger_csrf)])
def salvar_agenda(chave: str, dados: ConfiguracaoAgenda, request: Request,
                  usuario=Depends(exigir_permissao("configurar_sistema"))):
    if chave not in {"livro_protocolos", "intimacoes"}:
        raise HTTPException(404, "Agendamento não encontrado.")
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("""UPDATE automacoes_operacionais_aeri SET habilitada=%s,intervalo_minutos=%s,
                hora_inicio=%s,hora_fim=%s,dias_semana=%s,proxima_execucao=NOW(),atualizado_por=%s,
                atualizado_em=NOW() WHERE chave=%s""", (dados.habilitada,dados.intervalo_minutos,dados.hora_inicio,
                    dados.hora_fim,Jsonb(dados.dias_semana),usuario,chave))
            registrar_auditoria_cursor(cur,request,"configurar_agendamento","sucesso",usuario,chave,dados.model_dump())
        con.commit()
    return {"ok": True}


@router.get("/sistema/cron")
def cron(request: Request):
    segredo = os.getenv("CRON_SECRET", "")
    if len(segredo) < 32 or not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {segredo}"):
        raise HTTPException(401, "Executor não autorizado.")
    return {k:executar_passo(k) for k in ("intimacoes", "livro_protocolos")}


@router.get("/livro-protocolos/automatico")
def ultimo_livro(_usuario=Depends(exigir_permissao("acessar_livro_protocolos"))):
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT estado,resultado FROM execucoes_operacionais_aeri WHERE chave='livro_protocolos' ORDER BY inicio DESC LIMIT 1")
            r = cur.fetchone()
    if not r or "resumo" not in r["resultado"]:
        raise HTTPException(404, "Ainda não há resultado automático disponível.")
    resultado = {k:v for k,v in r["resultado"].items() if k != "fila"}
    return {**resultado, "estadoExecucao": r["estado"]}
