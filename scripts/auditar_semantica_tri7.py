import argparse
import csv
import json
import os
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.parser import separar_atos
from backend.app.proprietarios import (
    MARCADOR_PAPEL_NAO_ADQUIRENTE,
    extrair_bloco,
    extrair_pessoas,
    extrair_proprietario_inicial,
    extrair_retificacoes_cpf,
    nomes_compativeis,
    parse_percent,
)
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.tri7 import (
    ClienteTri7,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
)


CAMPOS = [
    "numero_matricula",
    "status",
    "situacao_aeri",
    "resultado_onus_aeri",
    "onus_explicitos",
    "onus_classificados",
    "onus_ativos",
    "onus_cancelados",
    "onus_ativos_sem_tipo",
    "cancelamentos_explicitos",
    "cancelamentos_sem_alvo",
    "cancelamentos_alvo_divergente",
    "onus_explicitos_codigos",
    "onus_classificados_codigos",
    "onus_ativos_codigos",
    "onus_explicitos_nao_classificados_codigos",
    "onus_ativos_nao_confirmados_codigos",
    "cancelamentos_sem_alvo_codigos",
    "cancelamentos_alvo_divergente_codigos",
    "marcador_matricula_inexistente",
    "marcador_encerramento_explicito",
    "marcador_desmembramento_integral",
    "marcador_lote",
    "extraiu_lote",
    "marcador_quadra",
    "extraiu_quadra",
    "marcador_area",
    "extraiu_area",
    "marcador_area_construida",
    "extraiu_area_construida",
    "marcador_cci",
    "extraiu_cci",
    "marcador_cep",
    "extraiu_cep",
    "marcador_ccir",
    "extraiu_ccir",
    "marcador_car",
    "extraiu_car",
    "marcador_rua",
    "extraiu_rua",
    "marcador_numero_predial",
    "extraiu_numero_predial",
    "marcador_setor",
    "extraiu_setor",
    "marcador_denominacao_rural",
    "extraiu_denominacao_rural",
    "marcador_incra",
    "extraiu_incra",
    "cabecalho_proprietario",
    "proprietarios_numerados_cabecalho",
    "proprietarios_extraidos_cabecalho",
    "indicacao_titularidade_declarados",
    "atos_transferencia",
    "atos_adquirente_rotulado",
    "atos_adquirente_nao_extraido",
    "proprietarios_extraidos",
    "proprietarios_sem_documento",
    "documentos_tamanho_invalido",
    "titularidade_total",
    "ultima_transferencia_integral_candidatos",
    "ultima_transferencia_integral_coberta",
    "retificacoes_cpf_atuais_nao_aplicadas",
    "veredito_onus",
    "veredito_cadeia",
    "veredito_imovel",
    "alertas_onus",
    "alertas_cadeia",
    "alertas_imovel",
    "evidencias_onus",
    "evidencias_cadeia",
    "evidencias_imovel",
    "confianca_onus",
    "confianca_cadeia",
    "confianca_imovel",
    "prioridade_revisao",
    "estado_auditoria",
    "alertas",
    "duracao_ms",
    "erro",
]
STATUS_TERMINAIS = {"OK", "NAO_ENCONTRADA", "SEM_TEXTO", "IGNORADA_LOTEAMENTO"}
TERMOS_TRANSFERENCIA = (
    "COMPRA E VENDA",
    "VENDA E COMPRA",
    "DOACAO",
    "PARTILHA",
    "SOBREPARTILHA",
    "ADJUDICACAO",
    "ARREMATACAO",
    "DACAO",
    "TITULO DE DOMINIO",
    "CONSOLIDACAO DA PROPRIEDADE",
    "INTEGRALIZACAO",
    "INCORPORACAO DE BENS",
    "PERMUTA",
    "DIVISAO",
    "REFORMA AGRARIA",
    "USUCAPIAO",
    "INVENTARIO",
    "REGULARIZACAO FUNDIARIA",
    "LEGITIMACAO FUNDIARIA",
)

ALERTAS_CRITICOS_ONUS = {
    "ONUS_EXPLICITO_NAO_CLASSIFICADO",
    "CANCELAMENTO_DE_ONUS_SEM_ALVO",
    "CANCELAMENTO_DE_ONUS_COM_ALVO_DIVERGENTE",
    "CANCELAMENTO_POSSIVELMENTE_INCOMPLETO",
    "RESULTADO_ONUS_INCONSISTENTE",
}
ALERTAS_CRITICOS_CADEIA = {
    "PROPRIETARIO_CABECALHO_NAO_EXTRAIDO",
    "CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA",
    "ADQUIRENTE_ROTULADO_NAO_EXTRAIDO",
    "PROPRIETARIOS_NUMERADOS_CABECALHO_NAO_EXTRAIDOS",
    "PROPRIETARIOS_PLURAIS_CABECALHO_NAO_EXTRAIDOS",
    "INDICACAO_TITULARIDADE_QUANTIDADE_DIVERGENTE",
    "TITULARIDADE_FORA_DE_100",
    "ULTIMA_TRANSFERENCIA_INTEGRAL_DIVERGENTE",
    "RETIFICACAO_CPF_NAO_APLICADA",
    "PROPRIETARIO_NOME_INVALIDO",
}
ALERTAS_CRITICOS_IMOVEL = {
    "ENCERRAMENTO_NAO_RECONHECIDO",
    "MATRICULA_INEXISTENTE_NAO_RECONHECIDA",
    "TIPO_IMOVEL_DIVERGENTE",
    "AREA_REGISTRAL_DIVERGENTE",
    "MATRICULA_NAO_IDENTIFICADA",
}


def carregar_env_local() -> None:
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha or linha.lstrip().startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor)


def sem_acentos(texto: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", str(texto or "").upper())
        if unicodedata.category(caractere) != "Mn"
    )


def cabecalho_matricula(texto: str) -> str:
    atos = separar_atos(texto)
    if not atos:
        return texto
    primeiro = texto.find(atos[0]["texto"])
    return texto[:primeiro] if primeiro >= 0 else texto


def contem_rotulo(itens: list[dict], rotulos: set[str]) -> bool:
    return any(item.get("rotulo") in rotulos and str(item.get("valor", "")).strip() for item in itens)


def item_por_rotulo(itens: list[dict], rotulo_normalizado: str) -> dict:
    return next(
        (
            item
            for item in itens
            if sem_acentos(item.get("rotulo", "")) == rotulo_normalizado
            and str(item.get("valor", "")).strip()
        ),
        {},
    )


def descricao_cabecalho_imovel(texto: str) -> str:
    cabecalho = sem_acentos(cabecalho_matricula(texto))
    bloco = re.search(
        r"\bIMOVEL\s*[:\-]\s*(.*?)"
        r"(?=\bP?ROPRIETARI[OA]S?\s*[:;]|\bTITULO\s+AQUISITIVO\s*:|\bORIGEM\s*:|$)",
        cabecalho,
        re.DOTALL,
    )
    return bloco.group(1) if bloco else cabecalho


def area_em_metros_quadrados(valor: str) -> float | None:
    correspondencia = re.search(
        r"([\d.]+(?:,\d+)?)\s*(M(?:2|²)|HA|HECTARES?)\b",
        sem_acentos(valor),
    )
    if not correspondencia:
        return None
    numero = float(correspondencia.group(1).replace(".", "").replace(",", "."))
    return numero * 10_000 if correspondencia.group(2).startswith(("HA", "HECTARE")) else numero


def area_registral_independente(texto: str) -> float | None:
    descricao = descricao_cabecalho_imovel(texto)
    totais_descritos = []
    for total in re.finditer(
        r"(?:PERFAZENDO\s+O\s+TOTAL\s+DE|TOTALIZANDO)\s*:?[ ]*"
        r"(\d+)(?:\s*\([^)]*\))?\s*HECTARES?"
        r"(?:\s*[,E]\s*(\d+)(?:\s*\([^)]*\))?\s*ARES?)?"
        r"(?:\s*,?\s*E\s*(\d+)(?:\s*\([^)]*\))?\s*CENTIARES?)?",
        descricao,
    ):
        totais_descritos.append(
            int(total.group(1))
            + int(total.group(2) or 0) / 100
            + int(total.group(3) or 0) / 10_000
        )
    if totais_descritos:
        return sum(totais_descritos) * 10_000

    composta = re.search(
        r"\bAREA(?:\s+TOTAL)?\s*(?:DE|:)?\s*(\d+)(?:\s*\([^)]*\))?\s*"
        r"HECTARES?\s*(?:,|E)\s*(\d+)(?:\s*\([^)]*\))?\s*ARES?"
        r"(?:\s+E\s*(\d+)(?:\s*\([^)]*\))?\s*(?:CENTIARES?)?)?",
        descricao,
    )
    if composta:
        hectares = (
            int(composta.group(1))
            + int(composta.group(2)) / 100
            + int(composta.group(3) or 0) / 10_000
        )
        return hectares * 10_000
    correspondencia = re.search(
        r"\bAREA(?:\s+TOTAL)?\s*(?:DE|:)?\s*"
        r"([\d.]+(?:,\d+)?)\s*(M(?:2|²)|HA|HECTARES?)\b",
        descricao,
    )
    if not correspondencia:
        return None
    return area_em_metros_quadrados(" ".join(correspondencia.groups()))


def evidencia_itens(itens: list[dict]) -> list[str]:
    evidencias = []
    for item in itens:
        rotulo = str(item.get("rotulo", "")).strip()
        origem = str(item.get("origem", "")).strip()
        if rotulo:
            evidencias.append(f"{rotulo}@{origem or 'origem não informada'}")
    return evidencias


def confianca_dominio(alertas: list[str], criticos: set[str]) -> str:
    if not alertas:
        return "ALTA"
    if criticos.intersection(alertas):
        return "BAIXA"
    return "MEDIA"


def contem_termo_transferencia(ato_normalizado: str) -> bool:
    return any(termo in ato_normalizado for termo in TERMOS_TRANSFERENCIA)


ROTULO_ADQUIRENTE_INDEPENDENTE = re.compile(
    r"\b(?:ADQUIRENTES?(?:/(?:TOMADOR(?:ES)?|"
    r"(?:PRIMEIR|SEGUND)[OA]S?\s+PERMUTANTES?))?|"
    r"OUTORGADOS?|DONAT[ÁA]RI[OA]S?|ADJUDICANTES?|"
    r"ARREMATANTES?|COMPRADOR(?:ES)?)\s*:\s*(.*?)"
    r"(?=\b(?:IM[ÓO]VEL|OBJETO|ORIGEM|FORMA\s+DO\s+T[ÍI]TULO|"
    r"TRANSMITENTES?|OUTORGANTES?|DOADORES?)\s*:|"
    + MARCADOR_PAPEL_NAO_ADQUIRENTE +
    r"|\*NOTA|\bDOU\s+F[ÉE]\b|$)",
    re.IGNORECASE | re.DOTALL,
)


def _documento_limpo(valor: object) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _percentual_numero(valor: object) -> float:
    try:
        return float(str(valor or "0").replace("%", "").replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _pessoa_presente(candidata: dict, proprietarios: list[dict]) -> bool:
    documento = _documento_limpo(candidata.get("cpf"))
    nome_candidato = sem_acentos(candidata.get("nome", "")).strip()
    for proprietario in proprietarios:
        documento_atual = _documento_limpo(proprietario.get("cpf"))
        if documento and documento_atual and documento == documento_atual:
            return True
        if nomes_compativeis(candidata.get("nome", ""), proprietario.get("nome", "")):
            return True
        nome_atual = sem_acentos(proprietario.get("nome", "")).strip()
        if (
            nome_candidato
            and nome_atual
            and SequenceMatcher(None, nome_candidato, nome_atual).ratio() >= 0.92
        ):
            return True
    return False


def auditar_proprietarios(texto: str, proprietarios: list[dict]) -> dict:
    atos_rotulados = 0
    atos_nao_extraidos = 0
    ultima_transferencia = None
    retificacoes_nao_aplicadas = 0
    cabecalho = cabecalho_matricula(texto)
    bloco_proprietarios = re.search(
        r'\b(?:P?ROPRIETARI|PRORIETARI)[OA]S?\s*[:;](.*?)(?=\bORIGEM\s*:|\*NOTA|\Z)',
        sem_acentos(cabecalho),
        re.DOTALL,
    )
    proprietarios_numerados = len(re.findall(
        r'(?:^|;)\s*(?:e\s*,?\s*)?(?:\d{1,3}\s*\)\s*-?|\d{1,3}\s+-)',
        bloco_proprietarios.group(1) if bloco_proprietarios else "",
        re.MULTILINE,
    ))
    proprietarios_por_percentual = len(re.findall(
        r'\(\s*\d+(?:[,.]\d+)?\s*%\s*\)',
        bloco_proprietarios.group(1) if bloco_proprietarios else "",
    ))
    proprietarios_numerados = max(
        proprietarios_numerados,
        proprietarios_por_percentual,
    )
    proprietarios_cabecalho = extrair_proprietario_inicial(cabecalho)
    indicacao_titularidade_declarados = 0

    for ato in separar_atos(texto):
        descricao = ato["texto"]
        normalizado = sem_acentos(descricao)
        transferencia = contem_termo_transferencia(normalizado)
        percentual_transferencia = parse_percent(descricao) if transferencia else 0.0
        if transferencia and percentual_transferencia <= 0 and re.search(
            r"\b(?:IMOVEL|OBJETO)\s*:\s*(?:O\s+)?(?:DESCRIT[OA]|OBJETO|CONSTANTE)"
            r".{0,80}\bMATRICULA\b|\bTOTALIDADE\s+DO\s+IMOVEL\b",
            normalizado,
            re.DOTALL,
        ):
            percentual_transferencia = 100.0
        bloco_independente = ROTULO_ADQUIRENTE_INDEPENDENTE.search(descricao)
        adquirentes = extrair_pessoas(extrair_bloco(descricao, "ADQUIRENTE"))
        if not adquirentes and bloco_independente:
            adquirentes = extrair_pessoas(bloco_independente.group(1))
        if transferencia:
            indicacao_titularidade_declarados = 0
        if "INDICA" in normalizado and "TITULARIDADE" in normalizado:
            quantidade_declarada = re.search(
                r'\b(\d{1,3})\s+PROPRIETARIOS?\s*100\s*%',
                normalizado,
            )
            if quantidade_declarada:
                indicacao_titularidade_declarados = int(quantidade_declarada.group(1))

        # Uma transmissão integral posterior recompõe toda a titularidade e
        # torna inócuas, para o estado atual, lacunas de atos integrais antigos.
        if transferencia and percentual_transferencia >= 99.0:
            atos_nao_extraidos = 0

        if bloco_independente and transferencia:
            atos_rotulados += 1
            documentos_declarados = {
                _documento_limpo(valor)
                for valor in re.findall(
                    r"(?:CPF|CNPJ|CIC|CGC)(?:/MF)?[^\d]{0,30}([\d.\-/]{9,20})",
                    bloco_independente.group(1),
                    re.IGNORECASE,
                )
                if _documento_limpo(valor)
            }
            documentos_extraidos = {
                _documento_limpo(pessoa.get("cpf"))
                for pessoa in adquirentes
                if _documento_limpo(pessoa.get("cpf"))
            }
            itens_numerados = len(re.findall(r"(?:^|;)\s*\d{1,3}\s*\)\s*-?", bloco_independente.group(1)))
            if documentos_declarados and (
                not adquirentes
                or (
                    not re.search(r"\bCOUBE\s+EXCLUSIVAMENTE\b", normalizado)
                    and itens_numerados
                    and len(adquirentes) < itens_numerados
                )
            ):
                atos_nao_extraidos += 1

        if transferencia:
            ultima_transferencia = {
                "percentual": percentual_transferencia,
                "adquirentes": adquirentes,
            }

        for retificada in extrair_retificacoes_cpf(descricao):
            atuais_mesmo_nome = [
                atual
                for atual in proprietarios
                if nomes_compativeis(retificada.get("nome", ""), atual.get("nome", ""))
            ]
            if atuais_mesmo_nome and not any(
                _documento_limpo(atual.get("cpf")) == _documento_limpo(retificada.get("cpf"))
                for atual in atuais_mesmo_nome
            ):
                retificacoes_nao_aplicadas += 1

        if "RETIFICACAO" in normalizado[:350] and "QUALIFICACAO" in normalizado[:350]:
            retificacao_direta = re.search(
                r"\bPROPRIETARI[OA]\s+([A-Z][A-Z\s'.-]{2,100}?)\s+"
                r"(?:E\s+)?(?:PORTADOR|PORTADORA|INSCRITO|INSCRITA)\b"
                r".{0,260}?\bCPF(?:/MF)?\b[^\d]{0,30}([\d.\-/]{9,20})",
                normalizado,
                re.DOTALL,
            )
            if retificacao_direta:
                nome_retificado = retificacao_direta.group(1).strip()
                documento_retificado = _documento_limpo(retificacao_direta.group(2))
                atuais_mesmo_nome = [
                    atual
                    for atual in proprietarios
                    if nomes_compativeis(nome_retificado, atual.get("nome", ""))
                ]
                if atuais_mesmo_nome and not any(
                    _documento_limpo(atual.get("cpf")) == documento_retificado
                    for atual in atuais_mesmo_nome
                ):
                    retificacoes_nao_aplicadas += 1

    candidatos_integrais = 0
    transferencia_integral_coberta = True
    if ultima_transferencia and ultima_transferencia["percentual"] >= 99.0:
        candidatos = ultima_transferencia["adquirentes"]
        candidatos_integrais = len(candidatos)
        if candidatos:
            transferencia_integral_coberta = all(
                _pessoa_presente(candidata, proprietarios) for candidata in candidatos
            )

    documentos = [_documento_limpo(item.get("cpf")) for item in proprietarios]
    total = sum(_percentual_numero(item.get("proporcao")) for item in proprietarios)
    return {
        "atos_adquirente_rotulado": atos_rotulados,
        "atos_adquirente_nao_extraido": atos_nao_extraidos,
        "proprietarios_numerados_cabecalho": proprietarios_numerados,
        "proprietarios_extraidos_cabecalho": len(proprietarios_cabecalho),
        "indicacao_titularidade_declarados": indicacao_titularidade_declarados,
        "proprietarios_sem_documento": sum(not documento for documento in documentos),
        "documentos_tamanho_invalido": sum(
            bool(documento) and len(documento) not in {9, 11, 14} for documento in documentos
        ),
        "titularidade_total": round(total, 4),
        "ultima_transferencia_integral_candidatos": candidatos_integrais,
        "ultima_transferencia_integral_coberta": transferencia_integral_coberta,
        "retificacoes_cpf_atuais_nao_aplicadas": retificacoes_nao_aplicadas,
    }


MARCADORES_CANCELAMENTO = (
    "CANCELAMENTO",
    "FICA CANCELAD",
    "FIQUE CANCELAD",
    "LIBERADO DO GRAVAME",
    "LIBERADA DO GRAVAME",
    "LIBERACAO DO GRAVAME",
    "BAIXA DA HIPOTECA",
    "EXTINCAO DA DIVIDA",
    "EXTINCAO DE HIPOTECA",
    "DIVIDA ORIGINARIA FOI CONSIDERADA EXTINTA",
    "LEVANTAMENTO DE PENHORA",
    "LIBERACAO DE HIPOTECA",
    "LIBERACAO DA GARANTIA HIPOTECARIA",
    "LIBERADOS DO GRAVAME",
    "LIBERADAS DO GRAVAME",
    "DESVINCULACAO DE IMOVEL",
    "DESVINCULAD",
    "FICOU EXCLUIDO DA AV",
    "FICOU EXCLUIDA DA AV",
    "EXCLUSAO DE BENS VINCULADOS",
    "LIBERACAO DO IMOVEL VINCULADO",
    "PERMUTA DE BENS APENHORADOS",
    "PERMUTA DE BENS APENHADOS",
    "PERMUTA DE BENS VINCULADOS",
    "PERMUTA DE BENS HIPOTECADOS",
    "PERMUTA E LIBERACAO DOS BENS APENHADOS",
    "LIBERACAO DE BENS APENHADOS",
)


def _cancelamento_explicito(ato_normalizado: str) -> bool:
    cabecalho = ato_normalizado[:500]
    # Retificações frequentemente apenas reproduzem a palavra "cancelamento"
    # ao corrigir o texto de um ato anterior. Elas não promovem nova baixa.
    indice_retificacao = cabecalho.find("RETIFICACAO")
    indice_cancelamento = cabecalho.find("CANCELAMENTO")
    if (
        0 <= indice_retificacao < 180
        and (indice_cancelamento < 0 or indice_retificacao < indice_cancelamento)
    ):
        return False
    if "DESVINCULAD" in cabecalho and "PROAGRO" in cabecalho and not any(
        marcador in cabecalho
        for marcador in ("CANCELAMENTO", "LIBERACAO", "LEVANTAMENTO", "QUITACAO")
    ):
        return False
    fortes = (
        "LEVANTAMENTO DE PENHORA", "LIBERACAO DE HIPOTECA",
        "LIBERACAO DE BENS APENHADOS", "PERMUTA DE BENS APENHADOS",
        "PERMUTA DE BENS VINCULADOS", "PERMUTA DE BENS HIPOTECADOS",
        "PERMUTA E LIBERACAO DOS BENS APENHADOS",
        "LIBERACAO DA GARANTIA HIPOTECARIA",
        "LIBERADOS DO GRAVAME",
        "LIBERADAS DO GRAVAME", "E LIBERADO DA GARANTIA O IMOVEL",
        "FOI LIBERADO DA GARANTIA O IMOVEL",
        "DESVINCULACAO DE IMOVEL", "DESVINCULAD", "FICOU EXCLUIDO DA AV",
        "FICOU EXCLUIDA DA AV", "EXCLUSAO DE BENS VINCULADOS",
        "CANCELAMENTO",
    )
    if any(marcador in cabecalho[:120] for marcador in (
        "SUBSTITUICAO DE GARANTIA",
        "DESISTENCIA DE USUFRUTO",
        "RENUNCIA DE USUFRUTO",
        "RENUNCIA DO USUFRUTO",
        "RENUNCIA AO USUFRUTO",
    )):
        return True
    if "COMPRA E VENDA COM DESISTENCIA DE USUFRUTO" in cabecalho[:320]:
        return True
    if any(marcador in cabecalho for marcador in fortes):
        return True
    if "RETIFICACAO" in cabecalho[:220]:
        return False
    return any(marcador in cabecalho for marcador in MARCADORES_CANCELAMENTO)


def _ato_constitui_onus(ato_normalizado: str) -> bool:
    """Leitura independente e conservadora dos sinais constitutivos do ato."""
    cabecalho = ato_normalizado[:600]
    cabecalho_formal = cabecalho.split("NOS TERMOS", 1)[0]
    if _cancelamento_explicito(ato_normalizado) or "RETIFICACAO DE CPF" in cabecalho:
        return False
    if any(marcador in cabecalho[:260] for marcador in (
        "INSERCAO DE DADOS DE QUALIFICACAO PESSOAL",
        "ATUALIZACAO DE DADOS DE QUALIFICACAO PESSOAL",
        "RETIFICACAO DE DADOS DE QUALIFICACAO PESSOAL",
    )):
        return False
    if re.search(
        r"\b(?:INCLUID[AO]|ACRESCID[AO]|CONSTITUID[AO])\b.{0,100}\b"
        r"(?:HIPOTECA|ALIENACAO FIDUCIARIA|GARANTIA)\b",
        ato_normalizado,
    ):
        return True
    if re.search(
        r"\bCONFISSAO\s+E\s+ASSUNCAO\s+DE\s+DIVIDAS?\b.{0,80}\b"
        r"GARANTIAS?\s+(?:PIGNORATICIA\s+E\s+)?HIPOTECARIA\b",
        cabecalho,
    ):
        return True
    if re.search(
        r"\b(?:DAO|DA|DADO|DADA|DADOS|DADAS)\s+EM\s+HIPOTECA\b",
        ato_normalizado,
    ):
        return True
    # Aditivos de retificação/ratificação preservam o gravame original.
    # Só são constitutivos quando o próprio texto declara inclusão, acréscimo
    # ou constituição de nova garantia (tratado logo acima).
    if "ADITIVO" in cabecalho_formal and re.search(
        r"\b(?:RE[ -]?RATIFICACAO|RETIFICACAO(?:\s+E\s+RATIFICACAO)?|RATIFICACAO)\b",
        cabecalho,
    ):
        return False
    if any(expressao in cabecalho_formal for expressao in (
        "CLAUSULAS DE INALIENABILIDADE E IMPENHORABILIDADE",
        "INALIENABILIDADE E IMPENHORABILIDADE",
        "CLAUSULA DE INCOMUNICABILIDADE",
    )):
        return False
    if re.search(
        r"\bANUENCIA(?:\s+DO\s+CREDOR\s+HIPOTECARIO)?\s*[.:]",
        cabecalho_formal[:220],
    ):
        return False
    if any(expressao in cabecalho[:350] for expressao in (
        "LIBERACAO DE IMOVEL",
        "LIBERACAO E SUBSTITUICAO DA AREA HIPOTECADA",
        "TRANSFERENCIA DE HIPOTECA",
        "SUB ROGACAO DE DIVIDA HIPOTECARIA",
        "SUB SUB ROGACAO DE DIVIDA HIPOTECARIA",
        "DESMEMBRAMENTO E MATRICULA",
        "RATIFICACAO DE AREA",
        "RETIFICACAO DE AREA",
        "LIBERACAO DE IMOVEL HIPOTECADO",
        "REPACTUACAO DA DIVIDA",
        "PRORROGACAO DE PRAZO",
        "EXCLUSAO DE BENS VINCULADOS",
        "QUITACAO DE PROMISSORIA",
        "INDICACAO GRAUS E CREDORES",
        "ALTERACAO DE CREDOR",
    )):
        return False
    if re.search(
        r"\bDIVIDA\b.{0,100}\bFOI\s+TRANSFERIDA\s+INTEGRALMENTE\b",
        cabecalho,
    ):
        return False
    if (
        "ADITIVO" in cabecalho[:180]
        and "RATIFIC" in ato_normalizado
        and any(marcador in ato_normalizado for marcador in (
            "VENCIMENTO",
            "FORMA DE PAGAMENTO",
            "ENCARGOS FINANCEIROS",
            "DATA DA PRIMEIRA PARCELA",
        ))
        and not re.search(
            r"\b(?:INCLUID[AO]|ACRESCID[AO]|CONSTITUID[AO])\b.{0,100}\b"
            r"(?:HIPOTECA|ALIENACAO FIDUCIARIA|GARANTIA)\b",
            ato_normalizado,
        )
    ):
        return False
    if any(expressao in cabecalho[:320] for expressao in (
        "RENEGOCIACAO",
        "REPACTUACAO",
        "ALTERACAO DO PRAZO",
        "ALTERACOES NO PRAZO",
        "ALTERACAO NO PRAZO DE VENCIMENTO",
        "ALTERACAO DO PRAZO DE VENCIMENTO",
        "ALTERACAO DE PRAZO DE VENCIMENTO",
        "ALTERACAO DO VENCIMENTO",
        "CONFISSAO DA DIVIDA, ALTERACAO DO VENCIMENTO",
        "ALTERACAO DE ENCARGOS FINANCEIROS",
        "INCORPORACAO AO PRINCIPAL",
        "RETIFICACAO EX-OFFICIO",
        "RETIFICACAO EX OFFICIO",
        "RETIFICACAO DA DENOMINACAO DA CEDULA",
        "TRANSFERENCIA DE CREDITO",
        "CESSAO DE CREDITO HIPOTECARIO",
        "COMISSAO DE PERMANENCIA",
        "ATUALIZACAO DO CERTIFICADO DE CADASTRO DE IMOVEL RURAL",
        "DESIGNACAO CADASTRAL DO IMOVEL",
        "ENDERECAMENTO POSTAL",
        "INSCRICAO NO CAR",
        "DIREITOS DECORRENTES DE ALIENACAO FIDUCIARIA",
    )):
        return False
    menciona_titulo_transmissao = any(termo in cabecalho[:500] for termo in (
        "COMPRA E VENDA",
        "VENDA E COMPRA",
        "DOACAO",
        "INVENTARIO",
        "PARTILHA",
        "ADJUDICACAO",
        "ARREMATACAO",
        "CONSOLIDACAO DA PROPRIEDADE",
    ))
    transferencia_principal = menciona_titulo_transmissao
    titulo_onus_explicito = any(termo in cabecalho[:250] for termo in (
        "HIPOTECA.",
        "ALIENACAO FIDUCIARIA.",
        "USUFRUTO:",
        "USUFRUTO VITALICIO",
        "PENHORA.",
        "MUTUO COM OBRIGACOES E HIPOTECA",
        "MUTUO COM OBRIGACOES E ALIENACAO FIDUCIARIA",
        "RESERVA DE USUFRUTO",
        "OBJETO DA GARANTIA",
        "CREDOR FIDUCIARIO",
        "CREDORA FIDUCIARIA",
    )) or bool(re.search(
        r"\bHIPOTECA(?:\s+DE\s+\d{1,2}[º°O]?\s+GRAU|\s*[.:])",
        cabecalho[:220],
    ))
    usufruto_reservado_na_transmissao = any(expressao in ato_normalizado for expressao in (
        "RESERVA DE USUFRUTO",
        "RESERVA PARA SI O DIREITO AO USUFRUTO",
        "RESERVARAM PARA SI O DIREITO DO USUFRUTO",
    ))
    onus_no_titulo_da_transmissao = any(expressao in cabecalho[:280] for expressao in (
        "ALIENACAO FIDUCIARIA",
        "GARANTIA HIPOTECARIA",
        "CONSTITUICAO DE GARANTIA HIPOTECARIA",
    ))
    if (
        transferencia_principal
        and not titulo_onus_explicito
        and not usufruto_reservado_na_transmissao
        and not onus_no_titulo_da_transmissao
    ):
        return False
    if any(expressao in ato_normalizado for expressao in (
        "PROPRIEDADE FIDUCIARIA",
        "EM ALIENACAO FIDUCIARIA",
        "GARANTIA FIDUCIARIA",
    )) and any(expressao in ato_normalizado for expressao in (
        "OBJETO DA GARANTIA", "CREDOR FIDUCIARIO", "CREDORA FIDUCIARIA",
    )):
        return True
    if "ALIENACAO FIDUCIARIA" in ato_normalizado:
        constitui = any(expressao in ato_normalizado for expressao in (
            "OBJETO DA GARANTIA",
            "CREDOR FIDUCIARIO",
            "CREDORA FIDUCIARIA",
            "PROPRIEDADE FIDUCIARIA",
            "EM ALIENACAO FIDUCIARIA",
            "GARANTIA FIDUCIARIA",
        )) or "ALIENACAO FIDUCIARIA" in cabecalho
        if constitui:
            return True

    if "HIPOTECA" in ato_normalizado:
        constitui = any(expressao in ato_normalizado for expressao in (
            "DADO EM HIPOTECA",
            "DADA EM HIPOTECA",
            "EM HIPOTECA",
            "GARANTIA HIPOTECARIA",
            "CEDULA RURAL HIPOTECARIA",
            "CEDULA HIPOTECARIA",
            "OBJETO DA GARANTIA",
            "FOI HIPOTECADO",
        )) or ("HIPOTECA" in cabecalho and not transferencia_principal)
        if constitui:
            return True

    if re.search(r"\bPENHORA\b", ato_normalizado):
        return "PENHORA" in cabecalho[:300] or bool(re.search(
            r"(?:FICA|FOI|E)\s+PENHORAD|PROCEDE-SE.{0,80}\bPENHORA\b",
            ato_normalizado,
        ))

    if re.search(r"\bPENHOR\b", ato_normalizado):
        return (
            "PENHOR" in cabecalho[:300]
            or "DADO EM PENHOR" in ato_normalizado
            or "BENS APENHADOS LOCALIZADOS NO IMOVEL" in ato_normalizado
        )

    if "VINCULAD" in cabecalho[:350] and "CEDULA" in ato_normalizado:
        return True

    if "USUFRUTO" in ato_normalizado:
        return "USUFRUTO" in cabecalho or any(expressao in ato_normalizado for expressao in (
            "RESERVA DE USUFRUTO",
            "RESERVOU PARA SI O USUFRUTO",
            "RESERVARAM PARA SI O DIREITO DO USUFRUTO",
            "RESERVARAM PARA SI O USUFRUTO",
            "CONSTITUI USUFRUTO",
            "INSTITUI USUFRUTO",
        ))

    if "SERVIDAO" in ato_normalizado:
        return "SERVIDAO" in cabecalho[:300] or any(expressao in ato_normalizado for expressao in (
            "CONSTITUI SERVIDAO",
            "INSTITUI SERVIDAO",
            "SERVIDAO DE PASSAGEM",
            "FICA CONSERVADA A SERVIDAO EXISTENTE",
        ))

    titulos_onus = (
        "ANTICRESE",
        "ARRESTO",
        "SEQUESTRO",
        "ASSUNCAO DE DIVIDA",
        "ASSUNCAO DE OBRIGACAO",
        "CAUCAO",
        "FIDEICOMISSO",
        "COMPROMISSO DE COMPRA E VENDA",
        "CONCESSAO DE DIREITO",
        "CONCESSAO DE USO",
        "ABERTURA DE CREDITO",
        "CEDULA DE CREDITO",
        "CEDULA DE PRODUTO RURAL",
        "CEDULA RURAL",
        "DEBENTURES",
        "DIREITO DE SUPERFICIE",
        "ENFITEUSE",
        "NOTA DE CREDITO",
        "UTILIZACAO COMPULSORIA",
        "RENDAS CONSTITUIDAS",
        "RENOVACAO SIMPLIFICADA",
        "TERMO DE SECURITIZACAO",
    )
    return any(titulo in cabecalho[:350] for titulo in titulos_onus)


def auditar_onus(texto: str, resultado: dict) -> dict:
    atos_texto = separar_atos(texto)
    atos_aeri = resultado.get("atos") or []
    explicitos = []
    cancelamentos = []
    for ato in atos_texto:
        normalizado = sem_acentos(ato["texto"])
        cancelamento = _cancelamento_explicito(normalizado)
        if cancelamento:
            cancelamentos.append(ato["codigo"])
        elif _ato_constitui_onus(normalizado):
            explicitos.append(ato["codigo"])

    classificados = [
        ato for ato in atos_aeri if sem_acentos(ato.get("categoria", "")) == "ONUS"
    ]
    ativos = [ato for ato in classificados if ato.get("status") == "ATIVO"]
    cancelados = [ato for ato in classificados if ato.get("status") == "CANCELADO"]
    codigos_classificados = {str(ato.get("codigo", "")) for ato in classificados}
    codigos_explicitos = set(explicitos)
    faltantes = sorted(codigos_explicitos - codigos_classificados)
    extras_ativos = sorted(
        str(ato.get("codigo", "")) for ato in ativos
        if str(ato.get("codigo", "")) not in codigos_explicitos
    )
    sem_tipo = [ato for ato in ativos if not ato.get("tipo_onus")]
    cancelamentos_sem_alvo = []
    cancelamentos_alvo_divergente = []
    cancelamentos_possivelmente_incompletos = []

    def codigo_normalizado(valor: object) -> str:
        correspondencia = re.search(r"\b(R|AV)\s*[.\-,]*\s*(\d+)", str(valor or ""), re.IGNORECASE)
        return f"{correspondencia.group(1).upper()}.{int(correspondencia.group(2))}" if correspondencia else ""

    por_codigo = {
        codigo_normalizado(ato.get("codigo")): ato for ato in atos_aeri
    }
    posicoes = {id(ato): indice for indice, ato in enumerate(atos_aeri)}
    codigos_onus_normalizados = {
        codigo_normalizado(ato.get("codigo")) for ato in classificados
    }
    identificacao = (resultado.get("imovel") or {}).get("identificacao") or []
    valor_matricula = next(
        (item.get("valor", "") for item in identificacao if item.get("rotulo") == "Matrícula"),
        "",
    )
    numero_matricula = re.sub(r"\D", "", str(valor_matricula))
    for codigo in cancelamentos:
        ato = por_codigo.get(codigo_normalizado(codigo)) or {}
        descricao = sem_acentos(ato.get("descricao", ""))
        menciona_gravame = bool(re.search(
            r"\b(?:HIPOTECA|ALIENACAO\s+FIDUCIARIA|PENHORA|PENHOR|USUFRUTO|SERVIDAO)\b",
            descricao,
        ))
        if "PENHOR RURAL/IMOVEL DE LOCALIZACAO" in descricao[:220]:
            menciona_gravame = False
        if any(marcador in descricao[:600] for marcador in (
            "CLAUSULAS DE INALIENABILIDADE E IMPENHORABILIDADE",
            "CLAUSULA DE INALIENABILIDADE E IMPENHORABILIDADE",
        )):
            menciona_gravame = False
        referencias = set()
        for referencia in re.finditer(
            r"\b(R|AV)\s*[.\-,]*\s*(\d+)(?!\d|\.\d)(?:\s*-\s*(\d{1,10}))?",
            descricao,
            re.IGNORECASE,
        ):
            sufixo = referencia.group(3)
            if sufixo and numero_matricula and str(int(sufixo)) != str(int(numero_matricula)):
                continue
            referencias.add(codigo_normalizado(f"{referencia.group(1)}.{referencia.group(2)}"))
        alvos_esperados = set()
        for referencia in referencias:
            if referencia in codigos_onus_normalizados:
                alvos_esperados.add(referencia)
                continue
            tipo, numero = referencia.split(".", 1)
            inversa = f"{'AV' if tipo == 'R' else 'R'}.{numero}"
            if inversa in codigos_onus_normalizados:
                alvos_esperados.add(inversa)
        alvos_aplicados = {
            codigo_normalizado(alvo) for alvo in (ato.get("cancela_atos") or [])
        }
        referencia_externa = bool(re.search(
            r"\b(?:R|AV)\s*[.\-,]*\s*\d+\s*-\s*(\d{1,10})\b",
            descricao,
        ) and any(
            str(int(sufixo)) != str(int(numero_matricula))
            for sufixo in re.findall(
                r"\b(?:R|AV)\s*[.\-,]*\s*\d+\s*-\s*(\d{1,10})\b",
                descricao,
            )
            if numero_matricula
        ))
        if (
            menciona_gravame
            and not referencia_externa
            and not alvos_aplicados.intersection(codigos_onus_normalizados)
        ):
            cancelamentos_sem_alvo.append(codigo)
        if alvos_esperados and not alvos_esperados.issubset(alvos_aplicados):
            cancelamentos_alvo_divergente.append(codigo)
        tipos_cancelados = {
            tipo
            for marcador, tipo in (
                ("USUFRUTO", "USUFRUTO"),
                ("HIPOTECA", "HIPOTECA"),
                ("ALIENACAO FIDUCIARIA", "ALIENACAO FIDUCIARIA"),
                ("PENHORA", "PENHORA"),
                ("SERVIDAO", "SERVIDAO"),
            )
            if marcador in descricao
            and re.search(rf"\bCANCELAD[AO]\b.{{0,80}}\b{marcador}\b", descricao)
        }
        # Sem uma referência textual, o motor pode ter baixado apenas uma das
        # representações duplicadas do mesmo gravame (ex.: doação com reserva
        # e registro autônomo do usufruto). Quando o ato indica R./AV. específico,
        # outro ônus anterior do mesmo tipo é independente e não constitui erro.
        if tipos_cancelados and not alvos_esperados and any(
            sem_acentos(ativo.get("tipo_onus", "")) in tipos_cancelados
            and posicoes.get(id(ativo), -1) < posicoes.get(id(ato), len(atos_aeri))
            for ativo in ativos
        ):
            cancelamentos_possivelmente_incompletos.append(codigo)

    alertas = []
    if faltantes:
        alertas.append("ONUS_EXPLICITO_NAO_CLASSIFICADO")
    if extras_ativos:
        alertas.append("ONUS_ATIVO_SEM_CONSTITUICAO_INDEPENDENTE")
    if sem_tipo:
        alertas.append("ONUS_ATIVO_SEM_TIPO")
    if cancelamentos_sem_alvo:
        alertas.append("CANCELAMENTO_DE_ONUS_SEM_ALVO")
    if cancelamentos_alvo_divergente:
        alertas.append("CANCELAMENTO_DE_ONUS_COM_ALVO_DIVERGENTE")
    if cancelamentos_possivelmente_incompletos:
        alertas.append("CANCELAMENTO_POSSIVELMENTE_INCOMPLETO")
    resultado_positivo = str(resultado.get("resultado", "")).startswith("POSITIVA")
    if resultado_positivo != bool(ativos):
        alertas.append("RESULTADO_ONUS_INCONSISTENTE")

    return {
        "resultado_onus_aeri": resultado.get("resultado", ""),
        "onus_explicitos": len(explicitos),
        "onus_classificados": len(classificados),
        "onus_ativos": len(ativos),
        "onus_cancelados": len(cancelados),
        "onus_ativos_sem_tipo": len(sem_tipo),
        "cancelamentos_explicitos": len(cancelamentos),
        "cancelamentos_sem_alvo": len(cancelamentos_sem_alvo),
        "cancelamentos_alvo_divergente": len(cancelamentos_alvo_divergente),
        "onus_explicitos_codigos": ",".join(explicitos),
        "onus_classificados_codigos": ",".join(str(ato.get("codigo", "")) for ato in classificados),
        "onus_ativos_codigos": ",".join(str(ato.get("codigo", "")) for ato in ativos),
        "onus_explicitos_nao_classificados_codigos": ",".join(faltantes),
        "onus_ativos_nao_confirmados_codigos": ",".join(extras_ativos),
        "cancelamentos_sem_alvo_codigos": ",".join(cancelamentos_sem_alvo),
        "cancelamentos_alvo_divergente_codigos": ",".join(cancelamentos_alvo_divergente),
        "alertas_onus": ";".join(alertas),
    }


def marcadores_independentes(texto: str) -> dict:
    cabecalho = cabecalho_matricula(texto)
    cabecalho_normalizado = sem_acentos(cabecalho)
    texto_normalizado = sem_acentos(texto)
    atos = separar_atos(texto)
    atos_normalizados = [sem_acentos(item["texto"]) for item in atos]
    cabecalho_do_imovel = re.split(
        r"\bP?ROPRIETARI[OA]S?\s*[:;]|\bTITULO\s+AQUISITIVO\s*:|\bORIGEM\s*:",
        cabecalho_normalizado,
        maxsplit=1,
    )[0]
    bloco_imovel = re.search(
        r"\bIMOVEL\s*[:\-]\s*(.*?)(?=\bP?ROPRIETARI[OA]S?\s*[:;]|\bTITULO\s+AQUISITIVO\s*:|\bORIGEM\s*:|$)",
        cabecalho_do_imovel,
        re.DOTALL,
    )
    descricao_imovel = bloco_imovel.group(1) if bloco_imovel else cabecalho_do_imovel
    contexto_inicial = descricao_imovel[:260]
    denominacao_rural = bool(re.search(
        r"\b(?:FAZENDA|CHACARA|SITIO|ESTANCIA)\b",
        contexto_inicial,
    )) and not bool(re.search(r"\b(?:LOTE|QUADRA)\b", contexto_inicial))
    contexto_urbano = bool(re.search(
        r"\b(?:LOTE|QUADRA|RUA|AVENIDA|ALAMEDA|TRAVESSA|PRACA|VIELA|BECO)\b",
        contexto_inicial,
    ))
    candidatos_numero_predial = list(re.finditer(
        r"\b(?:RUA|AVENIDA|ALAMEDA|TRAVESSA|PRACA|RODOVIA|VIELA|BECO)\b"
        r"(?P<entre>[^;]{0,100}?)[,\s]+N(?:UMERO)?[.\s\xBA\xB0O]*\d+",
        descricao_imovel[:300],
    ))
    numero_predial = any(
        not re.search(r"\b(?:LOTE|QUADRA)\b", candidato.group("entre"))
        for candidato in candidatos_numero_predial
    )

    ccir_com_codigo = any(
        "CCIR" in ato
        and bool(re.search(
            r"(?:CODIGO\s+DO\s+IMOVEL\s+RURAL|N[.\sº°O]*DO\s+CCIR)"
            r"[^\d]{0,80}\d",
            ato,
        ))
        for ato in atos_normalizados
    )

    encerramento_explicito = bool(re.search(
        r"(?:FICA|FICANDO|FOI|E|SEJA)?(?:\s+EM\s+CONSEQUENCIA)?\s*"
        r"ENCERRAD[AO]\s+(?:A\s+)?(?:PRESENTE\s+|ESTA\s+)?MATRICULA"
        r"|COM\s+O\s+QUE\s+(?:FICA\s+)?ENCERRAD[AO]"
        r"|ENCERRA-SE\s+(?:A\s+)?(?:PRESENTE\s+)?MATRICULA"
        r"|ENCERRAMENTO\s+(?:DA\s+)?(?:PRESENTE\s+)?MATRICULA"
        r"|CANCELAMENTO\s+(?:DA\s+|DE\s+)?MATRICULA"
        r"|FICA\s+CANCELAD[AO]\s+(?:A\s+|O\s+)?(?:PRESENTE\s+)?MATRICULA",
        texto_normalizado,
    ))
    desmembramento_integral = bool(re.search(
        r"DESMEMBRAMENTO\s+DO\s+IMOVEL(?:\s+OBJETO\s+DA\s+PRESENTE\s+MATRICULA"
        r"|\s+MATRICULADO)?\s+EM\s+"
        r"(?:DUAS|TRES|QUATRO|CINCO|SEIS|SETE|OITO|NOVE|DEZ|\d+)\s+GLEBAS\b",
        texto_normalizado,
    )) and "REMANESC" not in texto_normalizado

    return {
        "marcador_matricula_inexistente": (
            "SALTO NA NUMERACAO SEQUENCIAL DE MATRICULAS" in texto_normalizado
            and bool(re.search(r"NAO\s+EXISTE(?:M)?\s+CARACTERISTICAS\s+DE\s+IMOV(?:EL|EIS)", texto_normalizado))
        ),
        "marcador_encerramento_explicito": encerramento_explicito,
        "marcador_desmembramento_integral": desmembramento_integral,
        "marcador_lote": bool(re.search(r"\bLOTE(?:\s+DE\s+TERRAS)?\s+N", descricao_imovel)),
        "marcador_quadra": bool(re.search(r"\bQUADRA\s+N", descricao_imovel)),
        "marcador_area": bool(re.search(r"\bAREA\s+(?:TOTAL\s+)?(?:DE\s*)?[\d.,]+\s*(?:M[²2]|HA|HECTARE)", descricao_imovel)),
        "marcador_area_construida": any(
            ("AREA CONSTRUIDA" in ato or "AREA TOTAL CONSTRUIDA" in ato)
            and "DEMOLI" not in ato
            and any(termo in ato[:250] for termo in ("EDIFICACAO", "CONSTRUCAO", "RECONSTRUCAO", "ACRESCIMO"))
            for ato in atos_normalizados[
                max(
                    (indice for indice, ato in enumerate(atos_normalizados) if "DEMOLI" in ato),
                    default=-1,
                ) + 1:
            ]
        ),
        "marcador_cci": (
            bool(re.search(r"\bCCI\b", cabecalho_normalizado))
            or any(re.search(r"\bCCI\b", ato) and "CADASTR" in ato for ato in atos_normalizados)
        ),
        "marcador_cep": any(
            "ENDERECAMENTO POSTAL" in ato
            or "CEP DO IMOVEL" in ato
            or re.search(r"\bIMOVEL\b.{0,100}\bPOSSUI\b.{0,100}\bCEP\b", ato, re.DOTALL)
            for ato in atos_normalizados
        ) or bool(re.search(r"\bCEP\b", descricao_imovel)),
        "marcador_ccir": ccir_com_codigo,
        "marcador_car": any("CADASTRO AMBIENTAL RURAL" in ato or "INSCRICAO NO CAR" in ato for ato in atos_normalizados),
        "marcador_rua": bool(re.search(
            r"\b(?:RUA|AVENIDA|ALAMEDA|TRAVESSA|PRACA|RODOVIA|VIELA|BECO)\b",
            descricao_imovel[:260],
        )),
        "marcador_numero_predial": numero_predial,
        "marcador_setor": contexto_urbano and not denominacao_rural and bool(re.search(
            r"\b(?:SETOR|BAIRRO|JARDIM|VILA|LOTEAMENTO)\b",
            contexto_inicial,
        )),
        "marcador_denominacao_rural": denominacao_rural,
        "marcador_incra": bool(re.search(
            r"\bINCRA\b[^\n;]{0,220}(?:"
            r"\bSOB\s+O\s+N[.\s\xBA\xB0O]*[\d.]|"
            r"\bCODIGO\s+DO\s+IMOVEL\s+RURAL\s*[:;]?\s*[\d.]"
            r")",
            cabecalho_normalizado,
        )),
        "cabecalho_proprietario": bool(re.search(r"\b(?:P?ROPRIETARI|PRORIETARI)[OA]S?\s*[:;]", cabecalho_normalizado)),
        "atos_transferencia": sum(contem_termo_transferencia(ato) for ato in atos_normalizados),
    }


def auditar_texto(numero: int, texto: str, resultado: dict | None = None) -> dict:
    inicio = time.monotonic()
    resultado = resultado or analisar_matricula(texto, numero_matricula=str(numero))
    imovel = resultado.get("imovel") or {}
    identificacao = imovel.get("identificacao") or []
    areas = imovel.get("areas") or []
    cadastros = imovel.get("cadastros") or []
    proprietarios = resultado.get("proprietarios_atuais") or []
    marcadores = marcadores_independentes(texto)
    auditoria_proprietarios = auditar_proprietarios(texto, proprietarios)
    auditoria_onus = auditar_onus(texto, resultado)

    extraidos = {
        "extraiu_lote": contem_rotulo(identificacao, {"Lote"}),
        "extraiu_quadra": contem_rotulo(identificacao, {"Quadra"}),
        "extraiu_area": contem_rotulo(areas, {"Área"}),
        "extraiu_area_construida": contem_rotulo(areas, {"Área Construída"}),
        "extraiu_cci": any("CCI" in str(item.get("valor", "")).upper() for item in cadastros),
        "extraiu_cep": contem_rotulo(cadastros, {"CEP"}),
        "extraiu_ccir": contem_rotulo(cadastros, {"CCIR / código rural"}),
        "extraiu_car": contem_rotulo(cadastros, {"CAR"}),
        "extraiu_rua": contem_rotulo(identificacao, {"Rua"}),
        "extraiu_numero_predial": contem_rotulo(identificacao, {"Número"}),
        "extraiu_setor": contem_rotulo(identificacao, {"Setor"}),
        "extraiu_denominacao_rural": contem_rotulo(identificacao, {"Denominação", "Nome"}),
        "extraiu_incra": contem_rotulo(cadastros, {"INCRA"}),
    }
    situacao = str((imovel.get("situacao") or {}).get("status", ""))
    tipo_imovel = sem_acentos(imovel.get("tipo", ""))
    alertas_imovel = []
    if (marcadores["marcador_encerramento_explicito"] or marcadores["marcador_desmembramento_integral"]) and situacao != "ENCERRADA":
        alertas_imovel.append("ENCERRAMENTO_NAO_RECONHECIDO")
    if marcadores["marcador_matricula_inexistente"] and situacao != "INEXISTENTE":
        alertas_imovel.append("MATRICULA_INEXISTENTE_NAO_RECONHECIDA")
    for nome in (
        "lote", "quadra", "area", "area_construida", "cci", "cep", "ccir", "car",
        "rua", "numero_predial", "setor", "denominacao_rural", "incra",
    ):
        if tipo_imovel == "RURAL" and nome in {"rua", "numero_predial", "setor"}:
            continue
        if tipo_imovel == "URBANO" and nome in {"ccir", "car", "denominacao_rural", "incra"}:
            continue
        if marcadores[f"marcador_{nome}"] and not extraidos[f"extraiu_{nome}"]:
            alertas_imovel.append(f"{nome.upper()}_NAO_EXTRAIDO")

    descricao_imovel = descricao_cabecalho_imovel(texto)
    if (
        tipo_imovel == "RURAL"
        and re.search(r"\bLOTE\b", descricao_imovel[:350])
        and re.search(r"\bQUADRA\b", descricao_imovel[:350])
        and re.search(r"\b(?:NESTA\s+CIDADE|RUA|AVENIDA|LOTEAMENTO)\b", descricao_imovel[:350])
    ):
        alertas_imovel.append("TIPO_IMOVEL_DIVERGENTE")

    area_extraida = area_em_metros_quadrados(
        str(item_por_rotulo(areas, "AREA").get("valor", ""))
    )
    area_independente = area_registral_independente(texto)
    if (
        area_extraida is not None
        and area_independente is not None
        and abs(area_extraida - area_independente) > max(0.01, area_independente * 0.001)
    ):
        alertas_imovel.append("AREA_REGISTRAL_DIVERGENTE")

    rua_extraida = sem_acentos(item_por_rotulo(identificacao, "RUA").get("valor", ""))
    if re.match(
        r"^(RUA|AVENIDA|ALAMEDA|TRAVESSA|PRACA|RODOVIA|VIELA|BECO)\s+\1\b",
        rua_extraida,
    ):
        alertas_imovel.append("RUA_COM_PREFIXO_DUPLICADO")

    setor_extraido = str(item_por_rotulo(identificacao, "SETOR").get("valor", "")).strip()
    if (
        re.match(r"^(?:D[OA]\s+)?LOTEAMENTO\b", sem_acentos(setor_extraido))
        or re.match(r"^(SETOR|BAIRRO|RESIDENCIAL)\s+\1\b", sem_acentos(setor_extraido))
        or '"' in setor_extraido
        or "“" in setor_extraido
        or "”" in setor_extraido
    ):
        alertas_imovel.append("SETOR_COM_QUALIFICADOR_RESIDUAL")

    alertas_cadeia = []
    if marcadores["cabecalho_proprietario"] and not proprietarios:
        alertas_cadeia.append("PROPRIETARIO_CABECALHO_NAO_EXTRAIDO")
    if marcadores["atos_transferencia"] and not proprietarios:
        alertas_cadeia.append("CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA")
    if auditoria_proprietarios["atos_adquirente_nao_extraido"]:
        alertas_cadeia.append("ADQUIRENTE_ROTULADO_NAO_EXTRAIDO")
    if (
        auditoria_proprietarios["proprietarios_numerados_cabecalho"]
        > auditoria_proprietarios["proprietarios_extraidos_cabecalho"]
    ):
        alertas_cadeia.append("PROPRIETARIOS_NUMERADOS_CABECALHO_NAO_EXTRAIDOS")
    if (
        auditoria_proprietarios["indicacao_titularidade_declarados"]
        and len(proprietarios) != auditoria_proprietarios["indicacao_titularidade_declarados"]
    ):
        alertas_cadeia.append("INDICACAO_TITULARIDADE_QUANTIDADE_DIVERGENTE")
    if proprietarios and abs(auditoria_proprietarios["titularidade_total"] - 100.0) > 0.1:
        alertas_cadeia.append("TITULARIDADE_FORA_DE_100")
    if (
        auditoria_proprietarios["ultima_transferencia_integral_candidatos"]
        and not auditoria_proprietarios["ultima_transferencia_integral_coberta"]
    ):
        alertas_cadeia.append("ULTIMA_TRANSFERENCIA_INTEGRAL_DIVERGENTE")
    if auditoria_proprietarios["retificacoes_cpf_atuais_nao_aplicadas"]:
        alertas_cadeia.append("RETIFICACAO_CPF_NAO_APLICADA")
    if any(
        (
            len(re.sub(r"[^A-Z]", "", sem_acentos(item.get("nome", "")))) < 2
            or sem_acentos(item.get("nome", "")).strip()
            in {"DESCONHECIDO", "NAO INFORMADO", "NOME NAO INFORMADO"}
        )
        for item in proprietarios
    ):
        alertas_cadeia.append("PROPRIETARIO_NOME_INVALIDO")
    if not contem_rotulo(identificacao, {"Matrícula"}):
        alertas_imovel.append("MATRICULA_NAO_IDENTIFICADA")

    alertas_onus = list(filter(None, auditoria_onus["alertas_onus"].split(";")))
    alertas = alertas_onus + alertas_cadeia + alertas_imovel

    codigos_transferencia = [
        ato["codigo"]
        for ato in separar_atos(texto)
        if contem_termo_transferencia(sem_acentos(ato["texto"]))
    ]
    evidencias_onus = sorted(filter(None, {
        *str(auditoria_onus.get("onus_explicitos_codigos", "")).split(","),
        *str(auditoria_onus.get("onus_classificados_codigos", "")).split(","),
        *str(auditoria_onus.get("cancelamentos_sem_alvo_codigos", "")).split(","),
        *str(auditoria_onus.get("cancelamentos_alvo_divergente_codigos", "")).split(","),
    }))
    situacao_origem = str((imovel.get("situacao") or {}).get("origem", "")).strip()
    evidencias_imovel = evidencia_itens(identificacao + areas + cadastros)
    if situacao:
        evidencias_imovel.append(f"Situação@{situacao_origem or 'origem não informada'}")

    confianca_onus = confianca_dominio(alertas_onus, ALERTAS_CRITICOS_ONUS)
    confianca_cadeia = confianca_dominio(alertas_cadeia, ALERTAS_CRITICOS_CADEIA)
    confianca_imovel = confianca_dominio(alertas_imovel, ALERTAS_CRITICOS_IMOVEL)
    confiancas = {confianca_onus, confianca_cadeia, confianca_imovel}
    prioridade_revisao = (
        "P0-CRITICA"
        if "BAIXA" in confiancas
        else "P1-CONFERIR"
        if alertas
        else "P2-VALIDADA"
    )

    return {
        "numero_matricula": numero,
        "status": "OK",
        "situacao_aeri": situacao,
        **marcadores,
        **extraidos,
        **auditoria_proprietarios,
        **auditoria_onus,
        "proprietarios_extraidos": len(proprietarios),
        "veredito_onus": "REVISAR" if alertas_onus else "OK",
        "veredito_cadeia": "REVISAR" if alertas_cadeia else "OK",
        "veredito_imovel": "REVISAR" if alertas_imovel else "OK",
        "alertas_cadeia": ";".join(alertas_cadeia),
        "alertas_imovel": ";".join(alertas_imovel),
        "evidencias_onus": ",".join(evidencias_onus),
        "evidencias_cadeia": ",".join(codigos_transferencia),
        "evidencias_imovel": ";".join(evidencias_imovel),
        "confianca_onus": confianca_onus,
        "confianca_cadeia": confianca_cadeia,
        "confianca_imovel": confianca_imovel,
        "prioridade_revisao": prioridade_revisao,
        "estado_auditoria": "REVISAR" if alertas else "VALIDADA_AUTOMATICAMENTE",
        "alertas": ";".join(alertas),
        "duracao_ms": round((time.monotonic() - inicio) * 1000),
        "erro": "",
    }


class LimitadorTaxa:
    def __init__(self, requisicoes_por_segundo: float):
        self.intervalo = 1.0 / max(requisicoes_por_segundo, 0.1)
        self.proximo = 0.0
        self.trava = threading.Lock()

    def aguardar(self) -> None:
        with self.trava:
            agora = time.monotonic()
            reservado = max(agora, self.proximo)
            self.proximo = reservado + self.intervalo
        if reservado > agora:
            time.sleep(reservado - agora)


def linha_erro(numero: int, status: str, inicio: float, erro: str = "") -> dict:
    linha = {campo: "" for campo in CAMPOS}
    linha.update(
        numero_matricula=numero,
        status=status,
        prioridade_revisao="P0-CRITICA",
        estado_auditoria="NAO_PROCESSADA",
        duracao_ms=round((time.monotonic() - inicio) * 1000),
        erro=erro[:240],
    )
    return linha


def linha_ignorada_loteamento(numero: int) -> dict:
    linha = {campo: "" for campo in CAMPOS}
    linha.update(
        numero_matricula=numero,
        status="IGNORADA_LOTEAMENTO",
        situacao_aeri="IGNORADA",
        veredito_onus="IGNORADO",
        veredito_cadeia="IGNORADO",
        veredito_imovel="IGNORADO",
        confianca_onus="NAO_APLICAVEL",
        confianca_cadeia="NAO_APLICAVEL",
        confianca_imovel="NAO_APLICAVEL",
        prioridade_revisao="P2-VALIDADA",
        estado_auditoria="IGNORADA",
        erro="Registro de loteamento excluído da auditoria por decisão registral.",
    )
    return linha


def processar_numero(numero: int, cliente: ClienteTri7, limitador: LimitadorTaxa, tentativas: int) -> dict:
    inicio = time.monotonic()
    for tentativa in range(1, tentativas + 1):
        try:
            limitador.aguardar()
            texto = cliente.buscar_texto_matricula(numero)["texto"]
            return auditar_texto(numero, texto)
        except MatriculaTri7NaoEncontrada:
            return linha_erro(numero, "NAO_ENCONTRADA", inicio)
        except MatriculaTri7SemTexto:
            return linha_erro(numero, "SEM_TEXTO", inicio)
        except ErroTri7 as erro:
            if tentativa < tentativas:
                time.sleep(min(2 ** (tentativa - 1), 8))
                continue
            return linha_erro(numero, "ERRO_API", inicio, str(erro))
        except Exception as erro:
            return linha_erro(numero, "ERRO_PROCESSAMENTO", inicio, f"{type(erro).__name__}: {erro}")
    raise RuntimeError("Fluxo de tentativas inválido.")


def ler_resultados(caminho: Path) -> dict[int, dict]:
    if not caminho.exists():
        return {}
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return {int(linha["numero_matricula"]): linha for linha in csv.DictReader(arquivo)}


def filtrar_resultados_faixa(
    resultados: dict[int, dict], inicio: int, fim: int
) -> dict[int, dict]:
    """Evita que tentativas de outras faixas contaminem resumo e código de saída."""
    return {
        numero: linha
        for numero, linha in resultados.items()
        if inicio <= numero <= fim
    }


def gravar_resultados_consolidados(
    caminho: Path,
    resultados: dict[int, dict],
    inicio: int,
    fim: int,
) -> None:
    """Compacta o checkpoint, mantendo apenas a versão mais recente de cada matrícula."""
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        escritor.writeheader()
        for numero in range(inicio, fim + 1):
            linha = resultados.get(numero)
            if linha:
                escritor.writerow({campo: linha.get(campo, "") for campo in CAMPOS})
    os.replace(temporario, caminho)


def gravar_resumo(caminho: Path, resultados: dict[int, dict], inicio: int, fim: int) -> Path:
    totais_status: dict[str, int] = {}
    totais_alertas: dict[str, int] = {}
    exemplos_alertas: dict[str, list[int]] = {}
    totais_dominio = {"onus": 0, "cadeia": 0, "imovel": 0}
    totais_prioridade: dict[str, int] = {}
    totais_estado: dict[str, int] = {}
    for numero, linha in sorted(resultados.items()):
        status = linha.get("status", "")
        totais_status[status] = totais_status.get(status, 0) + 1
        for dominio in totais_dominio:
            if str(linha.get(f"alertas_{dominio}", "")).strip():
                totais_dominio[dominio] += 1
        prioridade = str(linha.get("prioridade_revisao", "")).strip() or "NAO_CLASSIFICADA"
        estado = str(linha.get("estado_auditoria", "")).strip() or "NAO_CLASSIFICADO"
        totais_prioridade[prioridade] = totais_prioridade.get(prioridade, 0) + 1
        totais_estado[estado] = totais_estado.get(estado, 0) + 1
        for alerta in filter(None, str(linha.get("alertas", "")).split(";")):
            totais_alertas[alerta] = totais_alertas.get(alerta, 0) + 1
            exemplos_alertas.setdefault(alerta, [])
            if len(exemplos_alertas[alerta]) < 100:
                exemplos_alertas[alerta].append(numero)
    resumo = {
        "faixa": {"inicio": inicio, "fim": fim, "quantidade": fim - inicio + 1},
        "totais_status": totais_status,
        "totais_dominio": totais_dominio,
        "totais_prioridade": totais_prioridade,
        "totais_estado_auditoria": totais_estado,
        "totais_alertas": totais_alertas,
        "exemplos_alertas": exemplos_alertas,
        "observacao": "Relatório técnico sem texto registral, nomes ou documentos pessoais.",
    }
    destino = caminho.with_name(f"{caminho.stem}-resumo.json")
    destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audita semanticamente os resultados do AERI na base Tri7.")
    parser.add_argument("--inicio", type=int, default=1)
    parser.add_argument("--fim", type=int, default=39_850)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--tentativas", type=int, default=4)
    parser.add_argument("--refazer", default="")
    parser.add_argument(
        "--ignorar-loteamentos",
        default="",
        help="Números separados por vírgula que representam loteamentos fora do escopo.",
    )
    parser.add_argument(
        "--refazer-alertas",
        action="store_true",
        help="Reprocessa somente registros que ainda possuem alertas no relatório informado.",
    )
    parser.add_argument(
        "--refazer-dominio",
        choices=("onus", "cadeia", "imovel"),
        help="Reprocessa somente os registros alertados no domínio informado.",
    )
    parser.add_argument(
        "--refazer-tipos",
        default="",
        help=(
            "Reprocessa somente registros que possuam ao menos um dos alertas "
            "informados, separados por vírgula."
        ),
    )
    parser.add_argument(
        "--base",
        type=Path,
        help="CSV usado como estado inicial, mantendo --saida independente.",
    )
    parser.add_argument("--saida", type=Path, default=RAIZ / "output" / "relatorios" / "auditoria_semantica_tri7.csv")
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio or not 1 <= args.workers <= 20:
        raise SystemExit("Faixa ou quantidade de workers inválida.")
    carregar_env_local()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    resultados_base = ler_resultados(args.base) if args.base else {}
    resultados_saida = ler_resultados(args.saida)
    anteriores = filtrar_resultados_faixa(
        {**resultados_base, **resultados_saida}, args.inicio, args.fim
    )
    ignorados = {
        int(item)
        for item in args.ignorar_loteamentos.split(",")
        if item.strip()
    }
    ignorados_novos = {
        numero
        for numero in ignorados
        if args.inicio <= numero <= args.fim
        and anteriores.get(numero, {}).get("status") != "IGNORADA_LOTEAMENTO"
    }
    for numero in ignorados_novos:
        anteriores[numero] = linha_ignorada_loteamento(numero)
    refazer = {int(item) for item in args.refazer.split(",") if item.strip()}
    if args.refazer_alertas:
        refazer.update(
            numero for numero, linha in anteriores.items()
            if str(linha.get("alertas", "")).strip()
        )
    if args.refazer_dominio:
        campo_dominio = f"alertas_{args.refazer_dominio}"
        refazer.update(
            numero for numero, linha in anteriores.items()
            if str(linha.get(campo_dominio, "")).strip()
        )
    tipos_refazer = {
        item.strip()
        for item in args.refazer_tipos.split(",")
        if item.strip()
    }
    if tipos_refazer:
        refazer.update(
            numero for numero, linha in anteriores.items()
            if tipos_refazer.intersection(
                filter(None, str(linha.get("alertas", "")).split(";"))
            )
        )
    concluidos = {
        numero for numero, linha in anteriores.items()
        if linha.get("status") in STATUS_TERMINAIS and numero not in refazer
    }
    pendentes = [numero for numero in range(args.inicio, args.fim + 1) if numero not in concluidos]
    cliente = ClienteTri7()
    limitador = LimitadorTaxa(args.rps)
    novo_arquivo = not args.saida.exists() or args.saida.stat().st_size == 0
    inicio_execucao = time.monotonic()
    ultimo_aviso = inicio_execucao
    processados = 0

    print(
        f"Iniciando auditoria {args.inicio}-{args.fim}: pendentes={len(pendentes)}, "
        f"workers={args.workers}, limite={args.rps:g} req/s",
        flush=True,
    )
    modo_abertura = "w" if novo_arquivo and anteriores else "a"
    with args.saida.open(modo_abertura, encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        if novo_arquivo:
            escritor.writeheader()
            for numero in sorted(anteriores):
                escritor.writerow({campo: anteriores[numero].get(campo, "") for campo in CAMPOS})
            arquivo.flush()
        else:
            for numero in sorted(ignorados_novos):
                escritor.writerow(anteriores[numero])
            if ignorados_novos:
                arquivo.flush()
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futuros = {
                executor.submit(processar_numero, numero, cliente, limitador, args.tentativas): numero
                for numero in pendentes
            }
            for futuro in as_completed(futuros):
                linha = futuro.result()
                escritor.writerow(linha)
                arquivo.flush()
                anteriores[int(linha["numero_matricula"])] = linha
                processados += 1
                agora = time.monotonic()
                if agora - ultimo_aviso >= 20 or processados == len(pendentes):
                    velocidade = processados / max(agora - inicio_execucao, 0.001)
                    restantes = len(pendentes) - processados
                    alertas = sum(bool(item.get("alertas")) for item in anteriores.values())
                    erros = sum(str(item.get("status", "")).startswith("ERRO") for item in anteriores.values())
                    print(
                        f"PROGRESSO {processados}/{len(pendentes)}; alertas={alertas}; erros={erros}; "
                        f"velocidade={velocidade:.1f}/s; eta={restantes / max(velocidade, .001) / 60:.1f}min",
                        flush=True,
                    )
                    ultimo_aviso = agora

    gravar_resultados_consolidados(
        args.saida,
        anteriores,
        args.inicio,
        args.fim,
    )
    resumo = gravar_resumo(args.saida, anteriores, args.inicio, args.fim)
    erros = sum(str(item.get("status", "")).startswith("ERRO") for item in anteriores.values())
    print(f"CONCLUÍDO relatório={args.saida} resumo={resumo} erros={erros}", flush=True)
    return 2 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
