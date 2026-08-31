import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from datetime import datetime
from zoneinfo import ZoneInfo


FASE_INICIAL = "INTIMACAO"
FASE_EDITAL = "EDITAL"
FASE_CONSOLIDACAO = "CONSOLIDACAO"
FASES_INTIMACAO = {FASE_INICIAL, FASE_EDITAL, FASE_CONSOLIDACAO}
VALOR_INICIAL_ONR = Decimal("530.07")


def _texto_normalizado(valor: str) -> str:
    texto = unicodedata.normalize("NFD", str(valor or ""))
    return "".join(caractere for caractere in texto if unicodedata.category(caractere) != "Mn").lower()


def validar_fase(valor: object, *, obrigatoria: bool = False) -> str | None:
    fase = str(valor or "").strip().upper()
    if not fase and not obrigatoria:
        return None
    if fase not in FASES_INTIMACAO:
        raise HTTPException(status_code=422, detail="Selecione uma fase válida para a intimação.")
    return fase


def fase_por_andamento(nome_andamento: str, fase_atual: str | None = None) -> str:
    """Avança a fase quando o andamento identifica inequivocamente a próxima etapa."""
    texto = _texto_normalizado(nome_andamento)
    atual = validar_fase(fase_atual) or FASE_INICIAL

    if "consolida" in texto or "intimacao positiva" in texto:
        return FASE_CONSOLIDACAO
    if "edital" in texto and atual != FASE_CONSOLIDACAO:
        return FASE_EDITAL
    return atual


def somar_dias_uteis(data_inicial: date, quantidade: int, feriados: set[date] | None = None) -> date:
    """Soma dias úteis no servidor, com calendário persistido e versionável."""
    feriados = feriados or set()
    atual = data_inicial
    adicionados = 0
    while adicionados < quantidade:
        atual += timedelta(days=1)
        if atual.weekday() < 5 and atual not in feriados:
            adicionados += 1
    return atual


def andamento_indica_intimacao_positiva(andamento: str) -> bool:
    """Reconhece a expressão independentemente de acentos e caixa."""
    return "intimacao positiva" in _texto_normalizado(andamento)


def intimacao_json(registro: dict) -> dict:
    valor_pago_registro = registro.get("valor_pago_onr")
    valor_usado_registro = registro.get("valor_usado")
    valor_pago = Decimal(str(registro.get("total_creditos", VALOR_INICIAL_ONR if valor_pago_registro is None else valor_pago_registro)))
    valor_usado = Decimal(str(registro.get("total_repasses", 0 if valor_usado_registro is None else valor_usado_registro)))
    return {
        "situacaoConferencia": situacao_conferencia(registro),
        "id": str(registro["id"]),
        "protocolo": registro["protocolo"],
        "credor": registro["credor"],
        "devedor": registro["devedor"],
        "nomeAndamento": registro["nome_andamento"],
        "ultimoAndamento": registro["ultimo_andamento"].isoformat(),
        "ultimaConferencia": (
            registro["ultima_conferencia"].isoformat()
            if registro["ultima_conferencia"]
            else None
        ),
        "historico": registro["historico"] or [],
        "fase": registro.get("fase"),
        "protocoloRtd": registro.get("protocolo_rtd"),
        "numeroOsTri7": registro.get("numero_os_tri7"),
        "protocoloTri7": registro.get("protocolo_tri7"),
        "certidaoDecursoPrazo": registro.get("certidao_decurso_prazo"),
        "dataIntimacao": (
            registro["data_intimacao"].isoformat()
            if registro.get("data_intimacao")
            else None
        ),
        "dataCertificacao": (
            registro["data_certificacao"].isoformat()
            if registro.get("data_certificacao")
            else None
        ),
        "valorPagoOnr": float(valor_pago),
        "valorUsado": float(valor_usado),
        "saldoOs": float(valor_pago - valor_usado),
        "excluidaEm": registro.get("excluida_em").isoformat() if registro.get("excluida_em") else None,
        "checklistDesistencia": registro.get("checklist_desistencia") or {},
        "atualizadoEm": registro["atualizado_em"].isoformat(),
    }


def situacao_conferencia(registro: dict, hoje: date | None = None) -> dict:
    """Regra visual preexistente da Rotina, comum à lista e ao painel."""
    hoje = hoje or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ultima = registro.get("ultima_conferencia")
    if not ultima:
        return dict(classe="vermelho", rotulo="Pendente", detalhe="Nunca conferida", ordem=0)
    if isinstance(ultima, str):
        ultima = date.fromisoformat(ultima[:10])
    dias = max(0, (hoje - ultima).days)
    if dias == 0:
        return dict(classe="verde", rotulo="Conferida", detalhe="Conferida hoje", ordem=3)
    if dias == 1:
        return dict(classe="amarelo", rotulo="Vence hoje", detalhe="Último check ontem", ordem=1)
    if dias <= 4:
        return dict(classe="vermelho", rotulo="Atrasada", detalhe=f"Sem check há {dias} dias", ordem=0)
    return dict(classe="cinza", rotulo="Sem atividade", detalhe=f"Sem check há {dias} dias", ordem=2)


def validar_intimacao(dados: dict) -> tuple[str, str, str, str, date, str]:
    protocolo = str(dados.get("protocolo", "")).strip().upper()
    credor = str(dados.get("credor", "")).strip()
    devedor = str(dados.get("devedor", "")).strip()
    nome_andamento = str(dados.get("nomeAndamento", "Não informado")).strip()
    try:
        andamento = date.fromisoformat(str(dados.get("ultimoAndamento", "")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Data do último andamento inválida.") from exc
    if not re.fullmatch(r"IN\d{8}C", protocolo):
        raise HTTPException(status_code=422, detail="Use o protocolo no padrão IN01625306C.")
    if not credor or not devedor or len(credor) > 160 or len(devedor) > 160:
        raise HTTPException(status_code=422, detail="Informe credor e devedor válidos.")
    if not nome_andamento or len(nome_andamento) > 160:
        raise HTTPException(status_code=422, detail="Informe o nome do último andamento.")
    fase_informada = validar_fase(dados.get("fase")) or FASE_INICIAL
    fase = fase_por_andamento(nome_andamento, fase_informada)
    return protocolo, credor, devedor, nome_andamento, andamento, fase


def validar_novo_andamento(dados: dict | None) -> str | None:
    if not dados or "nomeAndamento" not in dados:
        return None
    nome_andamento = str(dados["nomeAndamento"]).strip()
    if not nome_andamento or len(nome_andamento) > 160:
        raise HTTPException(status_code=422, detail="Informe um novo andamento válido.")
    return nome_andamento


def _validar_texto_opcional(dados: dict, campo: str, limite: int) -> str | None:
    valor = str(dados.get(campo, "") or "").strip()
    if len(valor) > limite:
        raise HTTPException(status_code=422, detail=f"O campo {campo} excede o limite permitido.")
    return valor or None


def _validar_data_opcional(dados: dict, campo: str) -> date | None:
    valor = str(dados.get(campo, "") or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"A data informada em {campo} é inválida.") from exc


def _validar_valor(dados: dict, campo: str, padrao: Decimal) -> Decimal:
    valor = dados.get(campo, padrao)
    if valor in (None, ""):
        return padrao
    try:
        numero = Decimal(str(valor)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail=f"O valor informado em {campo} é inválido.") from exc
    if not numero.is_finite() or numero < 0:
        raise HTTPException(status_code=422, detail=f"O valor informado em {campo} não pode ser negativo.")
    return numero


def validar_campos_fase_inicial(dados: dict) -> dict:
    protocolo_rtd = re.sub(r"\D", "", str(dados.get("protocoloRtd", "") or ""))
    if protocolo_rtd and len(protocolo_rtd) != 17:
        raise HTTPException(status_code=422, detail="O protocolo RTD deve possuir 17 dígitos.")

    return {
        "protocolo_rtd": protocolo_rtd or None,
        "numero_os_tri7": _validar_texto_opcional(dados, "numeroOsTri7", 40),
        "protocolo_tri7": _validar_texto_opcional(dados, "protocoloTri7", 40),
        "certidao_decurso_prazo": _validar_texto_opcional(dados, "certidaoDecursoPrazo", 160),
        "data_intimacao": _validar_data_opcional(dados, "dataIntimacao"),
        "data_certificacao": _validar_data_opcional(dados, "dataCertificacao"),
        "valor_pago_onr": _validar_valor(dados, "valorPagoOnr", VALOR_INICIAL_ONR),
        "valor_usado": _validar_valor(dados, "valorUsado", Decimal("0.00")),
    }
