import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.tri7 import (
    ClienteTri7,
    ConfiguracaoTri7,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
)
from scripts.auditar_semantica_tri7 import auditar_texto


NAO_CONSTA = "NÃO CONSTA"
STATUS_TERMINAIS = {"OK", "NAO_ENCONTRADA", "SEM_TEXTO"}
REGISTROS_LOTEAMENTO_CONFIRMADOS = {4964}

CAMPOS_MATRICULA = [
    "numero_matricula",
    "status_processamento",
    "situacao_imovel",
    "situacao_origem",
    "matriculas_sucessoras",
    "tipo_imovel",
    "possivel_registro_loteamento",
    "resultado_onus",
    "publicidade",
    "lote",
    "lote_origem",
    "quadra",
    "quadra_origem",
    "rua",
    "rua_origem",
    "numero_predial",
    "numero_predial_origem",
    "setor",
    "setor_origem",
    "nome_imovel_rural",
    "nome_imovel_rural_origem",
    "area_registral",
    "area_registral_origem",
    "area_construida",
    "area_construida_origem",
    "area_ccir",
    "area_ccir_origem",
    "area_declarada_car",
    "area_declarada_car_origem",
    "confrontacao_frente",
    "confrontacao_frente_origem",
    "confrontacao_lado_direito",
    "confrontacao_lado_direito_origem",
    "confrontacao_lado_esquerdo",
    "confrontacao_lado_esquerdo_origem",
    "confrontacao_fundos",
    "confrontacao_fundos_origem",
    "cadastro_municipal",
    "cadastro_municipal_origem",
    "cci",
    "cci_origem",
    "cep",
    "cep_origem",
    "ccir_codigo_rural",
    "ccir_codigo_rural_origem",
    "incra",
    "incra_origem",
    "car",
    "car_origem",
    "coordenadas_car",
    "coordenadas_car_origem",
    "restricoes_dados_ambientais",
    "restricoes_origens",
    "divergencias",
    "divergencias_origens",
    "alertas_imovel",
    "alertas_imovel_origens",
    "quantidade_proprietarios_atuais",
    "titularidade_total",
    "quantidade_atos_relevantes",
    "quantidade_onus_ativos",
    "quantidade_onus_cancelados",
    "veredito_onus",
    "veredito_cadeia_dominial",
    "veredito_dados_imovel",
    "confianca_onus",
    "confianca_cadeia_dominial",
    "confianca_dados_imovel",
    "prioridade_revisao",
    "estado_auditoria",
    "alertas_auditoria_onus",
    "alertas_auditoria_cadeia",
    "alertas_auditoria_imovel",
    "duracao_ms",
    "erro",
]

CAMPOS_PROPRIETARIO = [
    "numero_matricula",
    "status_processamento",
    "ordem",
    "nome",
    "documento",
    "tipo_documento",
    "proporcao",
]

CAMPOS_ATO = [
    "numero_matricula",
    "status_processamento",
    "ordem",
    "codigo_ato",
    "categoria",
    "tipo_onus",
    "grau_onus",
    "status_ato",
    "cancelado_por",
    "atos_cancelados",
    "impacta_resultado",
]

def carregar_env_local() -> None:
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha or linha.lstrip().startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor)


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


def _texto(valor) -> str:
    if valor is None:
        return NAO_CONSTA
    if isinstance(valor, bool):
        return "SIM" if valor else "NÃO"
    valor = str(valor).strip()
    return valor or NAO_CONSTA


def _itens_rotulo(itens: list[dict], rotulos: set[str]) -> list[dict]:
    return [item for item in itens if str(item.get("rotulo", "")) in rotulos]


def _juntar_itens(itens: list[dict], chave: str) -> str:
    valores = []
    for item in itens:
        valor = str(item.get(chave, "")).strip()
        if valor and valor not in valores:
            valores.append(valor)
    return " | ".join(valores) if valores else NAO_CONSTA


def _valor_e_origem(itens: list[dict], rotulos: set[str]) -> tuple[str, str]:
    encontrados = _itens_rotulo(itens, rotulos)
    return _juntar_itens(encontrados, "valor"), _juntar_itens(encontrados, "origem")


def _percentual_numerico(valor: object) -> float:
    texto = str(valor or "").strip().replace("%", "").replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _tipo_documento(documento: object) -> str:
    digitos = re.sub(r"\D", "", str(documento or ""))
    if len(digitos) == 11:
        return "CPF"
    if len(digitos) == 14:
        return "CNPJ"
    return NAO_CONSTA


def evidencias_registro_loteamento(texto: str) -> list[str]:
    cabecalho = re.split(
        r"(?im)(?:^|\n)[ \t-]*(?:R|AV)[.\-]\s*0*1\b|\bPROPRIET[ÁA]RI[OA]S?\s*[:;]",
        texto,
        maxsplit=1,
    )[0]
    descricao = re.split(r"\bIM[ÓO]VEL\s*:\s*", cabecalho, maxsplit=1, flags=re.IGNORECASE)
    descricao = descricao[1] if len(descricao) == 2 else cabecalho
    padroes = (
        ("OBJETO_LOTEAMENTO", descricao, r"^\s*(?:UM[A]?\s+)?LOTEAMENTO\b"),
        ("IMOVEL_OBJETO_LOTEAMENTO", descricao, r"\bIM[ÓO]VEL\s+OBJETO\s+D[OA]\s+LOTEAMENTO\b"),
        ("PLANO_LOTEAMENTO_CARACTERISTICAS", texto, r"\bPLANO\s+DE\s+LOTEAMENTO\s*:\s*CARACTER"),
        (
            "QUANTITATIVOS_LOTES_QUADRAS",
            texto,
            r"\bN[ÚU]MERO\s+DE\s+LOTES\b.{0,500}\bN[ÚU]MERO\s+DE\s+QUADRAS\b",
        ),
        ("TIPO_LOTEAMENTO_SEGUNDO_USO", texto, r"\bTIPO\s+DE\s+LOTEAMENTO\s+SEGUNDO\s+SEU\s+USO\b"),
        (
            "QUADRAS_TABULADAS",
            texto,
            r"(?im)^\s*LOTEAMENTO\b[^\r\n]{1,180}\r?\n\s*QUADRA\b",
        ),
        (
            "TOTAL_DE_LOTES",
            texto,
            r"\bLOTEAMENTO\b.{0,500}\b(?:TOTAL|N[ÚU]MERO)\s+DE\s+LOTES\b",
        ),
    )
    return [
        nome for nome, trecho, padrao in padroes
        if re.search(padrao, trecho, re.IGNORECASE | re.DOTALL)
    ]


def _possivel_registro_loteamento(texto: str) -> str:
    return "SIM" if evidencias_registro_loteamento(texto) else "NÃO"


def _matricula_vazia(numero: int, status: str, erro: str, duracao_ms: int) -> dict:
    linha = {campo: NAO_CONSTA for campo in CAMPOS_MATRICULA}
    linha.update(
        numero_matricula=numero,
        status_processamento=status,
        quantidade_proprietarios_atuais="0",
        titularidade_total="0%",
        quantidade_atos_relevantes="0",
        quantidade_onus_ativos="0",
        quantidade_onus_cancelados="0",
        duracao_ms=duracao_ms,
        erro=_texto(erro),
    )
    return linha


def achatar_resultado(numero: int, texto: str, resultado: dict, auditoria: dict, duracao_ms: int) -> dict:
    imovel = resultado.get("imovel") or {}
    situacao = imovel.get("situacao") or {}
    identificacao = imovel.get("identificacao") or []
    confrontacoes = imovel.get("confrontacoes") or []
    areas = imovel.get("areas") or []
    cadastros = imovel.get("cadastros") or []
    restricoes = imovel.get("restricoes") or []
    divergencias = imovel.get("divergencias") or []
    alertas = imovel.get("alertas") or []
    proprietarios = resultado.get("proprietarios_atuais") or []
    atos = resultado.get("atos") or []

    sucessoras = situacao.get("matriculas_sucessoras") or []
    if not sucessoras and situacao.get("matricula_sucessora"):
        sucessoras = [situacao["matricula_sucessora"]]

    linha = {campo: NAO_CONSTA for campo in CAMPOS_MATRICULA}
    linha.update(
        numero_matricula=numero,
        status_processamento="OK",
        situacao_imovel=_texto(situacao.get("status")),
        situacao_origem=_texto(situacao.get("origem")),
        matriculas_sucessoras=_texto(" | ".join(map(str, sucessoras))),
        tipo_imovel=_texto(imovel.get("tipo")),
        possivel_registro_loteamento=_possivel_registro_loteamento(texto),
        resultado_onus=_texto(resultado.get("resultado")),
        publicidade=_texto(resultado.get("publicidade")),
        quantidade_proprietarios_atuais=str(len(proprietarios)),
        titularidade_total=(
            f"{sum(_percentual_numerico(item.get('proporcao')) for item in proprietarios):.5f}"
            .rstrip("0").rstrip(".").replace(".", ",") + "%"
        ),
        quantidade_atos_relevantes=str(len(atos)),
        quantidade_onus_ativos=str(sum(
            item.get("categoria") == "ÔNUS" and item.get("status") == "ATIVO" for item in atos
        )),
        quantidade_onus_cancelados=str(sum(
            item.get("categoria") == "ÔNUS" and item.get("status") == "CANCELADO" for item in atos
        )),
        veredito_onus=_texto(auditoria.get("veredito_onus")),
        veredito_cadeia_dominial=_texto(auditoria.get("veredito_cadeia")),
        veredito_dados_imovel=_texto(auditoria.get("veredito_imovel")),
        confianca_onus=_texto(auditoria.get("confianca_onus")),
        confianca_cadeia_dominial=_texto(auditoria.get("confianca_cadeia")),
        confianca_dados_imovel=_texto(auditoria.get("confianca_imovel")),
        prioridade_revisao=_texto(auditoria.get("prioridade_revisao")),
        estado_auditoria=_texto(auditoria.get("estado_auditoria")),
        alertas_auditoria_onus=_texto(auditoria.get("alertas_onus")),
        alertas_auditoria_cadeia=_texto(auditoria.get("alertas_cadeia")),
        alertas_auditoria_imovel=_texto(auditoria.get("alertas_imovel")),
        duracao_ms=duracao_ms,
        erro=NAO_CONSTA,
    )

    mapeamentos = (
        ("lote", identificacao, {"Lote"}),
        ("quadra", identificacao, {"Quadra"}),
        ("rua", identificacao, {"Rua"}),
        ("numero_predial", identificacao, {"Número"}),
        ("setor", identificacao, {"Setor"}),
        ("nome_imovel_rural", identificacao, {"Nome", "Denominação"}),
        ("area_registral", areas, {"Área"}),
        ("area_construida", areas, {"Área Construída"}),
        ("area_ccir", areas, {"Área no CCIR"}),
        ("area_declarada_car", areas, {"Área declarada no CAR"}),
        ("confrontacao_frente", confrontacoes, {"Frente"}),
        ("confrontacao_lado_direito", confrontacoes, {"Lado Direito"}),
        ("confrontacao_lado_esquerdo", confrontacoes, {"Lado Esquerdo"}),
        ("confrontacao_fundos", confrontacoes, {"Fundos"}),
        ("cadastro_municipal", cadastros, {"Cadastro municipal"}),
        ("cep", cadastros, {"CEP"}),
        ("ccir_codigo_rural", cadastros, {"CCIR / código rural"}),
        ("incra", cadastros, {"INCRA"}),
        ("car", cadastros, {"CAR"}),
        ("coordenadas_car", cadastros, {"Coordenadas do CAR"}),
    )
    for campo, itens, rotulos in mapeamentos:
        linha[campo], linha[f"{campo}_origem"] = _valor_e_origem(itens, rotulos)

    itens_cci = [
        item for item in cadastros
        if item.get("rotulo") == "Cadastro municipal" and "CCI" in str(item.get("valor", "")).upper()
    ]
    linha["cci"] = _juntar_itens(itens_cci, "valor")
    linha["cci_origem"] = _juntar_itens(itens_cci, "origem")
    linha["restricoes_dados_ambientais"] = _juntar_itens(restricoes, "valor")
    linha["restricoes_origens"] = _juntar_itens(restricoes, "origem")
    linha["divergencias"] = _juntar_itens(divergencias, "valor")
    linha["divergencias_origens"] = _juntar_itens(divergencias, "origem")
    linha["alertas_imovel"] = _juntar_itens(alertas, "mensagem")
    linha["alertas_imovel_origens"] = _juntar_itens(alertas, "origem")
    return linha


def achatar_proprietarios(numero: int, status: str, proprietarios: list[dict]) -> list[dict]:
    if not proprietarios:
        return [{
            "numero_matricula": numero,
            "status_processamento": status,
            "ordem": NAO_CONSTA,
            "nome": NAO_CONSTA,
            "documento": NAO_CONSTA,
            "tipo_documento": NAO_CONSTA,
            "proporcao": NAO_CONSTA,
        }]
    return [
        {
            "numero_matricula": numero,
            "status_processamento": status,
            "ordem": indice,
            "nome": _texto(item.get("nome")),
            "documento": _texto(item.get("cpf")),
            "tipo_documento": _tipo_documento(item.get("cpf")),
            "proporcao": _texto(item.get("proporcao")),
        }
        for indice, item in enumerate(proprietarios, start=1)
    ]


def achatar_atos(numero: int, status: str, atos: list[dict]) -> list[dict]:
    if not atos:
        return [{
            "numero_matricula": numero,
            "status_processamento": status,
            "ordem": NAO_CONSTA,
            "codigo_ato": NAO_CONSTA,
            "categoria": NAO_CONSTA,
            "tipo_onus": NAO_CONSTA,
            "grau_onus": NAO_CONSTA,
            "status_ato": NAO_CONSTA,
            "cancelado_por": NAO_CONSTA,
            "atos_cancelados": NAO_CONSTA,
            "impacta_resultado": NAO_CONSTA,
        }]
    linhas = []
    for indice, item in enumerate(atos, start=1):
        linhas.append({
            "numero_matricula": numero,
            "status_processamento": status,
            "ordem": indice,
            "codigo_ato": _texto(item.get("codigo")),
            "categoria": _texto(item.get("categoria")),
            "tipo_onus": _texto(item.get("tipo_onus")),
            "grau_onus": _texto(item.get("grau_onus")),
            "status_ato": _texto(item.get("status")),
            "cancelado_por": _texto(item.get("cancelado_por")),
            "atos_cancelados": _texto(" | ".join(item.get("cancela_atos") or [])),
            "impacta_resultado": _texto(item.get("impacta_resultado")),
        })
    return linhas


def processar_numero(numero: int, cliente: ClienteTri7, limitador: LimitadorTaxa, tentativas: int) -> dict:
    inicio = time.monotonic()
    for tentativa in range(1, tentativas + 1):
        try:
            limitador.aguardar()
            texto = cliente.buscar_texto_matricula(numero)["texto"]
            resultado = analisar_matricula(texto, numero_matricula=str(numero))
            auditoria = auditar_texto(numero, texto, resultado=resultado)
            duracao_ms = round((time.monotonic() - inicio) * 1000)
            return {
                "numero_matricula": numero,
                "status_processamento": "OK",
                "matricula": achatar_resultado(numero, texto, resultado, auditoria, duracao_ms),
                "proprietarios": achatar_proprietarios(numero, "OK", resultado.get("proprietarios_atuais") or []),
                "atos": achatar_atos(numero, "OK", resultado.get("atos") or []),
            }
        except MatriculaTri7NaoEncontrada:
            status = "NAO_ENCONTRADA"
            break
        except MatriculaTri7SemTexto:
            status = "SEM_TEXTO"
            break
        except ErroTri7 as erro:
            if tentativa < tentativas:
                time.sleep(min(2 ** (tentativa - 1), 30))
                continue
            status = "ERRO_API"
            mensagem = str(erro)
            break
        except Exception as erro:
            status = "ERRO_PROCESSAMENTO"
            mensagem = f"{type(erro).__name__}: {erro}"
            break

    duracao_ms = round((time.monotonic() - inicio) * 1000)
    mensagem = locals().get("mensagem", "")
    return {
        "numero_matricula": numero,
        "status_processamento": status,
        "matricula": _matricula_vazia(numero, status, mensagem, duracao_ms),
        "proprietarios": achatar_proprietarios(numero, status, []),
        "atos": achatar_atos(numero, status, []),
    }


def ler_checkpoint(caminho: Path) -> dict[int, dict]:
    resultados = {}
    if not caminho.exists():
        return resultados
    with caminho.open("r", encoding="utf-8") as arquivo:
        for numero_linha, linha in enumerate(arquivo, start=1):
            try:
                item = json.loads(linha)
                resultados[int(item["numero_matricula"])] = item
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                if linha.strip() and numero_linha > 1:
                    continue
    return resultados


def corrigir_situacoes_sinalizadas(resultados: dict[int, dict]) -> int:
    """Aplica ao inventário a evidência independente de encerramento já auditada."""
    corrigidas = 0
    for item in resultados.values():
        if item.get("status_processamento") != "OK":
            continue
        matricula = item.get("matricula") or {}
        alertas_imovel = [
            alerta
            for alerta in str(matricula.get("alertas_auditoria_imovel") or "").split(";")
            if alerta and alerta != NAO_CONSTA
        ]
        if "ENCERRAMENTO_NAO_RECONHECIDO" not in alertas_imovel:
            continue

        matricula["situacao_imovel"] = "ENCERRADA"
        matricula["situacao_origem"] = "Texto registral"
        alertas_imovel.remove("ENCERRAMENTO_NAO_RECONHECIDO")
        matricula["alertas_auditoria_imovel"] = ";".join(alertas_imovel) or NAO_CONSTA
        matricula["veredito_dados_imovel"] = "REVISAR" if alertas_imovel else "OK"
        matricula["confianca_dados_imovel"] = "MEDIA" if alertas_imovel else "ALTA"

        alertas_por_dominio = (
            str(matricula.get("alertas_auditoria_onus") or NAO_CONSTA),
            str(matricula.get("alertas_auditoria_cadeia") or NAO_CONSTA),
            str(matricula.get("alertas_auditoria_imovel") or NAO_CONSTA),
        )
        tem_alerta = any(alerta != NAO_CONSTA for alerta in alertas_por_dominio)
        confiancas = {
            str(matricula.get("confianca_onus") or ""),
            str(matricula.get("confianca_cadeia_dominial") or ""),
            str(matricula.get("confianca_dados_imovel") or ""),
        }
        matricula["prioridade_revisao"] = (
            "P0-CRITICA" if "BAIXA" in confiancas
            else "P1-CONFERIR" if tem_alerta
            else "P2-VALIDADA"
        )
        matricula["estado_auditoria"] = "REVISAR" if tem_alerta else "VALIDADA_AUTOMATICAMENTE"
        corrigidas += 1
    return corrigidas


def compactar_checkpoint(caminho: Path, resultados: dict[int, dict]) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8", newline="\n") as arquivo:
        for numero in sorted(resultados):
            arquivo.write(json.dumps(
                resultados[numero], ensure_ascii=False, separators=(",", ":")
            ) + "\n")
    os.replace(temporario, caminho)


def aplicar_triagem_loteamentos(resultados: dict[int, dict], evidencias: Path) -> dict[str, int]:
    """Separa matrícula-mãe provável de lote que apenas replica o plano original."""
    if not evidencias.exists():
        return {}
    totais = {"SIM": 0, "REVISAR": 0, "NÃO": 0}
    with evidencias.open("r", encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha.get("status") != "OK" or linha.get("registro_loteamento") != "SIM":
                continue
            numero = int(linha["numero_matricula"])
            item = resultados.get(numero)
            if not item or item.get("status_processamento") != "OK":
                continue
            matricula = item["matricula"]
            if numero in REGISTROS_LOTEAMENTO_CONFIRMADOS:
                classificacao = "SIM"
            elif matricula.get("lote") == NAO_CONSTA:
                classificacao = "REVISAR"
            else:
                classificacao = "NÃO"
            matricula["possivel_registro_loteamento"] = classificacao
            totais[classificacao] += 1

    for numero in REGISTROS_LOTEAMENTO_CONFIRMADOS:
        item = resultados.get(numero)
        if item and item.get("status_processamento") == "OK":
            anterior = item["matricula"].get("possivel_registro_loteamento")
            item["matricula"]["possivel_registro_loteamento"] = "SIM"
            if anterior != "SIM":
                totais["SIM"] += 1
    return totais


def gravar_csv(caminho: Path, campos: list[str], linhas) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({campo: linha.get(campo, NAO_CONSTA) for campo in campos})
    os.replace(temporario, caminho)


def consolidar(destino: Path, resultados: dict[int, dict], inicio: int, fim: int) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    ordenados = [resultados[numero] for numero in range(inicio, fim + 1) if numero in resultados]
    gravar_csv(destino / "matriculas.csv", CAMPOS_MATRICULA, (item["matricula"] for item in ordenados))
    gravar_csv(
        destino / "cadeia_dominial.csv",
        CAMPOS_PROPRIETARIO,
        (linha for item in ordenados for linha in item["proprietarios"]),
    )
    gravar_csv(
        destino / "onus_restricoes_publicidade.csv",
        CAMPOS_ATO,
        (linha for item in ordenados for linha in item["atos"]),
    )
    linhas_matricula = [item["matricula"] for item in ordenados]
    gravar_csv(
        destino / "revisao_onus.csv",
        CAMPOS_MATRICULA,
        (linha for linha in linhas_matricula if linha.get("veredito_onus") == "REVISAR"),
    )
    gravar_csv(
        destino / "revisao_cadeia_dominial.csv",
        CAMPOS_MATRICULA,
        (linha for linha in linhas_matricula if linha.get("veredito_cadeia_dominial") == "REVISAR"),
    )
    gravar_csv(
        destino / "revisao_dados_imovel.csv",
        CAMPOS_MATRICULA,
        (linha for linha in linhas_matricula if linha.get("veredito_dados_imovel") == "REVISAR"),
    )
    gravar_csv(
        destino / "revisao_registros_loteamento.csv",
        CAMPOS_MATRICULA,
        (
            linha for linha in linhas_matricula
            if linha.get("possivel_registro_loteamento") == "REVISAR"
        ),
    )

    totais_status = {}
    for item in ordenados:
        status = item["status_processamento"]
        totais_status[status] = totais_status.get(status, 0) + 1
    totais_situacao = {}
    totais_loteamento = {}
    totais_vereditos = {"onus": {}, "cadeia_dominial": {}, "dados_imovel": {}}
    for linha in linhas_matricula:
        situacao = linha.get("situacao_imovel", NAO_CONSTA)
        totais_situacao[situacao] = totais_situacao.get(situacao, 0) + 1
        loteamento = linha.get("possivel_registro_loteamento", NAO_CONSTA)
        totais_loteamento[loteamento] = totais_loteamento.get(loteamento, 0) + 1
        for dominio, campo in (
            ("onus", "veredito_onus"),
            ("cadeia_dominial", "veredito_cadeia_dominial"),
            ("dados_imovel", "veredito_dados_imovel"),
        ):
            veredito = linha.get(campo, NAO_CONSTA)
            totais_vereditos[dominio][veredito] = totais_vereditos[dominio].get(veredito, 0) + 1
    resumo = {
        "faixa": {"inicio": inicio, "fim": fim, "quantidade": fim - inicio + 1},
        "matriculas_no_checkpoint": len(ordenados),
        "status": totais_status,
        "situacao_imovel": totais_situacao,
        "registro_loteamento": totais_loteamento,
        "vereditos": totais_vereditos,
        "linhas": {
            "matriculas": len(ordenados),
            "cadeia_dominial": sum(len(item["proprietarios"]) for item in ordenados),
            "onus_restricoes_publicidade": sum(len(item["atos"]) for item in ordenados),
        },
        "campos_ausentes": NAO_CONSTA,
        "observacao": (
            "O inventário armazena somente o resultado estruturado da análise. "
            "O texto registral integral não é persistido."
        ),
    }
    caminho_resumo = destino / "resumo.json"
    caminho_resumo.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho_resumo


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exporta o inventário registral completo da base Tri7.")
    parser.add_argument("--inicio", type=int, default=1)
    parser.add_argument("--fim", type=int, default=39_850)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--rps", type=float, default=6.0)
    parser.add_argument("--tentativas", type=int, default=6)
    parser.add_argument(
        "--timeout",
        type=int,
        help="Timeout excepcional da auditoria em segundos (3 a 300); não altera o AERI.",
    )
    parser.add_argument("--refazer", default="")
    parser.add_argument(
        "--saida",
        type=Path,
        default=RAIZ / "output" / "relatorios" / "inventario_registral-v1",
    )
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio or not 1 <= args.workers <= 20:
        raise SystemExit("Faixa ou quantidade de workers inválida.")
    if args.timeout is not None and not 3 <= args.timeout <= 300:
        raise SystemExit("O timeout excepcional deve estar entre 3 e 300 segundos.")
    carregar_env_local()
    args.saida.mkdir(parents=True, exist_ok=True)
    checkpoint = args.saida / "checkpoint.jsonl"
    resultados = ler_checkpoint(checkpoint)
    refazer = {int(item) for item in args.refazer.split(",") if item.strip()}
    concluidos = {
        numero for numero, item in resultados.items()
        if item.get("status_processamento") in STATUS_TERMINAIS and numero not in refazer
    }
    pendentes = [numero for numero in range(args.inicio, args.fim + 1) if numero not in concluidos]
    configuracao = ConfiguracaoTri7.do_ambiente()
    if args.timeout is not None:
        configuracao = replace(configuracao, timeout=args.timeout)
    cliente = ClienteTri7(configuracao)
    limitador = LimitadorTaxa(args.rps)
    inicio_execucao = time.monotonic()
    ultimo_aviso = inicio_execucao
    processados = 0

    print(
        f"Iniciando inventário {args.inicio}-{args.fim}: pendentes={len(pendentes)}, "
        f"workers={args.workers}, limite={args.rps:g} req/s",
        flush=True,
    )
    with checkpoint.open("a", encoding="utf-8", newline="\n") as arquivo:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futuros = {}
            fila = iter(pendentes)
            for _ in range(min(len(pendentes), args.workers * 3)):
                try:
                    numero = next(fila)
                except StopIteration:
                    break
                futuros[executor.submit(processar_numero, numero, cliente, limitador, args.tentativas)] = numero

            while futuros:
                concluidos_agora, _ = wait(futuros, return_when=FIRST_COMPLETED)
                for futuro in concluidos_agora:
                    futuros.pop(futuro)
                    item = futuro.result()
                    arquivo.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                    arquivo.flush()
                    resultados[int(item["numero_matricula"])] = item
                    processados += 1
                    try:
                        proximo = next(fila)
                    except StopIteration:
                        proximo = None
                    if proximo is not None:
                        futuros[executor.submit(
                            processar_numero, proximo, cliente, limitador, args.tentativas
                        )] = proximo

                agora = time.monotonic()
                if agora - ultimo_aviso >= 20 or processados == len(pendentes):
                    velocidade = processados / max(agora - inicio_execucao, 0.001)
                    restantes = len(pendentes) - processados
                    erros = sum(
                        str(item.get("status_processamento", "")).startswith("ERRO")
                        for item in resultados.values()
                    )
                    print(
                        f"PROGRESSO {processados}/{len(pendentes)}; base={len(resultados)}; "
                        f"erros={erros}; velocidade={velocidade:.2f}/s; "
                        f"eta={restantes / velocidade / 60:.1f}min" if velocidade else "eta=indisponível",
                        flush=True,
                    )
                    ultimo_aviso = agora

    triagem_loteamentos = aplicar_triagem_loteamentos(
        resultados,
        args.saida.parent / "registros_loteamento-v1.csv",
    )
    corrigidas = corrigir_situacoes_sinalizadas(resultados)
    compactar_checkpoint(checkpoint, resultados)
    resumo = consolidar(args.saida, resultados, args.inicio, args.fim)
    erros = sum(
        str(item.get("status_processamento", "")).startswith("ERRO")
        for numero, item in resultados.items()
        if args.inicio <= numero <= args.fim
    )
    print(
        f"CONCLUÍDO destino={args.saida} resumo={resumo} erros={erros} "
        f"situacoes_corrigidas={corrigidas} loteamentos={triagem_loteamentos}",
        flush=True,
    )
    return 2 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
