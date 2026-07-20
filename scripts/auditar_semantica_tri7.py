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
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.parser import separar_atos
from backend.app.proprietarios import (
    extrair_bloco,
    extrair_pessoas,
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
    "cabecalho_proprietario",
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
    "alertas",
    "duracao_ms",
    "erro",
]
STATUS_TERMINAIS = {"OK", "NAO_ENCONTRADA", "SEM_TEXTO"}
TERMOS_TRANSFERENCIA = (
    "COMPRA E VENDA",
    "VENDA E COMPRA",
    "DOACAO",
    "PARTILHA",
    "ADJUDICACAO",
    "ARREMATACAO",
    "DACAO",
    "TITULO DE DOMINIO",
    "CONSOLIDACAO DA PROPRIEDADE",
    "INTEGRALIZACAO",
    "PERMUTA",
    "USUCAPIAO",
    "INVENTARIO",
)


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


def contem_termo_transferencia(ato_normalizado: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(termo)}\b", ato_normalizado)
        for termo in TERMOS_TRANSFERENCIA
    )


ROTULO_ADQUIRENTE_INDEPENDENTE = re.compile(
    r"\b(?:ADQUIRENTES?|OUTORGADOS?|DONAT[ÁA]RI[OA]S?|ADJUDICANTES?|"
    r"ARREMATANTES?|COMPRADOR(?:ES)?)\s*:\s*(.*?)"
    r"(?=\b(?:IM[ÓO]VEL|OBJETO|ORIGEM|FORMA\s+DO\s+T[ÍI]TULO|"
    r"TRANSMITENTES?|OUTORGANTES?|DOADORES?)\s*:|\*NOTA|\bDOU\s+F[ÉE]\b|$)",
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
    for proprietario in proprietarios:
        documento_atual = _documento_limpo(proprietario.get("cpf"))
        if documento and documento_atual and documento == documento_atual:
            return True
        if nomes_compativeis(candidata.get("nome", ""), proprietario.get("nome", "")):
            return True
    return False


def auditar_proprietarios(texto: str, proprietarios: list[dict]) -> dict:
    atos_rotulados = 0
    atos_nao_extraidos = 0
    ultima_transferencia = None
    retificacoes_nao_aplicadas = 0

    for ato in separar_atos(texto):
        descricao = ato["texto"]
        normalizado = sem_acentos(descricao)
        transferencia = contem_termo_transferencia(normalizado)
        percentual_transferencia = parse_percent(descricao) if transferencia else 0.0
        bloco_independente = ROTULO_ADQUIRENTE_INDEPENDENTE.search(descricao)
        adquirentes = extrair_pessoas(extrair_bloco(descricao, "ADQUIRENTE"))

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
                not adquirentes or (itens_numerados and len(adquirentes) < itens_numerados)
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
        "proprietarios_sem_documento": sum(not documento for documento in documentos),
        "documentos_tamanho_invalido": sum(
            bool(documento) and len(documento) not in {9, 11, 14} for documento in documentos
        ),
        "titularidade_total": round(total, 4),
        "ultima_transferencia_integral_candidatos": candidatos_integrais,
        "ultima_transferencia_integral_coberta": transferencia_integral_coberta,
        "retificacoes_cpf_atuais_nao_aplicadas": retificacoes_nao_aplicadas,
    }


def marcadores_independentes(texto: str) -> dict:
    cabecalho = cabecalho_matricula(texto)
    cabecalho_normalizado = sem_acentos(cabecalho)
    texto_normalizado = sem_acentos(texto)
    atos = separar_atos(texto)
    atos_normalizados = [sem_acentos(item["texto"]) for item in atos]
    bloco_imovel = re.search(
        r"\bIMOVEL\s*[:\-]\s*(.*?)(?=\bP?ROPRIETARI[OA]S?\s*[:;]|\bTITULO\s+AQUISITIVO\s*:|\bORIGEM\s*:|$)",
        cabecalho_normalizado,
        re.DOTALL,
    )
    descricao_imovel = bloco_imovel.group(1) if bloco_imovel else cabecalho_normalizado

    encerramento_explicito = bool(re.search(
        r"(?:FICA|FICANDO|FOI|E|SEJA)?\s*ENCERRAD[AO]\s+(?:A\s+)?(?:PRESENTE\s+)?MATRICULA"
        r"|COM\s+O\s+QUE\s+(?:FICA\s+)?ENCERRAD[AO]"
        r"|ENCERRA-SE\s+(?:A\s+)?(?:PRESENTE\s+)?MATRICULA"
        r"|ENCERRAMENTO\s+(?:DA\s+)?(?:PRESENTE\s+)?MATRICULA",
        texto_normalizado,
    ))
    desmembramento_integral = bool(re.search(
        r"DESMEMBRAMENTO\s+DO\s+IMOVEL\s+MATRICULADO\s+EM\s+"
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
        "marcador_cci": any(re.search(r"\bCCI\b", ato) and "CADASTR" in ato for ato in atos_normalizados),
        "marcador_cep": any(
            "ENDERECAMENTO POSTAL" in ato
            or "CEP DO IMOVEL" in ato
            or re.search(r"\bIMOVEL\b.{0,100}\bPOSSUI\b.{0,100}\bCEP\b", ato, re.DOTALL)
            for ato in atos_normalizados
        ),
        "marcador_ccir": any(
            "CCIR" in ato and ("CODIGO DO IMOVEL RURAL" in ato or "N.º DO CCIR" in ato or "N. DO CCIR" in ato)
            for ato in atos_normalizados
        ),
        "marcador_car": any("CADASTRO AMBIENTAL RURAL" in ato or "INSCRICAO NO CAR" in ato for ato in atos_normalizados),
        "cabecalho_proprietario": bool(re.search(r"\bP?ROPRIETARI[OA]S?\s*[:;]", cabecalho_normalizado)),
        "atos_transferencia": sum(contem_termo_transferencia(ato) for ato in atos_normalizados),
    }


def auditar_texto(numero: int, texto: str) -> dict:
    inicio = time.monotonic()
    resultado = analisar_matricula(texto, numero_matricula=str(numero))
    imovel = resultado.get("imovel") or {}
    identificacao = imovel.get("identificacao") or []
    areas = imovel.get("areas") or []
    cadastros = imovel.get("cadastros") or []
    proprietarios = resultado.get("proprietarios_atuais") or []
    marcadores = marcadores_independentes(texto)
    auditoria_proprietarios = auditar_proprietarios(texto, proprietarios)

    extraidos = {
        "extraiu_lote": contem_rotulo(identificacao, {"Lote"}),
        "extraiu_quadra": contem_rotulo(identificacao, {"Quadra"}),
        "extraiu_area": contem_rotulo(areas, {"Área"}),
        "extraiu_area_construida": contem_rotulo(areas, {"Área Construída"}),
        "extraiu_cci": any("CCI" in str(item.get("valor", "")).upper() for item in cadastros),
        "extraiu_cep": contem_rotulo(cadastros, {"CEP"}),
        "extraiu_ccir": contem_rotulo(cadastros, {"CCIR / código rural"}),
        "extraiu_car": contem_rotulo(cadastros, {"CAR"}),
    }
    situacao = str((imovel.get("situacao") or {}).get("status", ""))
    alertas = []
    if (marcadores["marcador_encerramento_explicito"] or marcadores["marcador_desmembramento_integral"]) and situacao != "ENCERRADA":
        alertas.append("ENCERRAMENTO_NAO_RECONHECIDO")
    if marcadores["marcador_matricula_inexistente"] and situacao != "INEXISTENTE":
        alertas.append("MATRICULA_INEXISTENTE_NAO_RECONHECIDA")
    for nome in ("lote", "quadra", "area", "area_construida", "cci", "cep", "ccir", "car"):
        if marcadores[f"marcador_{nome}"] and not extraidos[f"extraiu_{nome}"]:
            alertas.append(f"{nome.upper()}_NAO_EXTRAIDO")
    if marcadores["cabecalho_proprietario"] and not proprietarios:
        alertas.append("PROPRIETARIO_CABECALHO_NAO_EXTRAIDO")
    if marcadores["atos_transferencia"] and not proprietarios:
        alertas.append("CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA")
    if auditoria_proprietarios["atos_adquirente_nao_extraido"]:
        alertas.append("ADQUIRENTE_ROTULADO_NAO_EXTRAIDO")
    if proprietarios and abs(auditoria_proprietarios["titularidade_total"] - 100.0) > 0.1:
        alertas.append("TITULARIDADE_FORA_DE_100")
    if (
        auditoria_proprietarios["ultima_transferencia_integral_candidatos"]
        and not auditoria_proprietarios["ultima_transferencia_integral_coberta"]
    ):
        alertas.append("ULTIMA_TRANSFERENCIA_INTEGRAL_DIVERGENTE")
    if auditoria_proprietarios["retificacoes_cpf_atuais_nao_aplicadas"]:
        alertas.append("RETIFICACAO_CPF_NAO_APLICADA")
    if not contem_rotulo(identificacao, {"Matrícula"}):
        alertas.append("MATRICULA_NAO_IDENTIFICADA")

    return {
        "numero_matricula": numero,
        "status": "OK",
        "situacao_aeri": situacao,
        **marcadores,
        **extraidos,
        **auditoria_proprietarios,
        "proprietarios_extraidos": len(proprietarios),
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
        duracao_ms=round((time.monotonic() - inicio) * 1000),
        erro=erro[:240],
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


def gravar_resumo(caminho: Path, resultados: dict[int, dict], inicio: int, fim: int) -> Path:
    totais_status: dict[str, int] = {}
    totais_alertas: dict[str, int] = {}
    exemplos_alertas: dict[str, list[int]] = {}
    for numero, linha in sorted(resultados.items()):
        status = linha.get("status", "")
        totais_status[status] = totais_status.get(status, 0) + 1
        for alerta in filter(None, str(linha.get("alertas", "")).split(";")):
            totais_alertas[alerta] = totais_alertas.get(alerta, 0) + 1
            exemplos_alertas.setdefault(alerta, [])
            if len(exemplos_alertas[alerta]) < 100:
                exemplos_alertas[alerta].append(numero)
    resumo = {
        "faixa": {"inicio": inicio, "fim": fim, "quantidade": fim - inicio + 1},
        "totais_status": totais_status,
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
    parser.add_argument("--fim", type=int, default=39_767)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument("--tentativas", type=int, default=4)
    parser.add_argument("--refazer", default="")
    parser.add_argument(
        "--refazer-alertas",
        action="store_true",
        help="Reprocessa somente registros que ainda possuem alertas no relatório informado.",
    )
    parser.add_argument("--saida", type=Path, default=RAIZ / "output" / "relatorios" / "auditoria_semantica_tri7.csv")
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio or not 1 <= args.workers <= 20:
        raise SystemExit("Faixa ou quantidade de workers inválida.")
    carregar_env_local()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    anteriores = filtrar_resultados_faixa(
        ler_resultados(args.saida), args.inicio, args.fim
    )
    refazer = {int(item) for item in args.refazer.split(",") if item.strip()}
    if args.refazer_alertas:
        refazer.update(
            numero for numero, linha in anteriores.items()
            if str(linha.get("alertas", "")).strip()
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
    with args.saida.open("a", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        if novo_arquivo:
            escritor.writeheader()
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

    resumo = gravar_resumo(args.saida, anteriores, args.inicio, args.fim)
    erros = sum(str(item.get("status", "")).startswith("ERRO") for item in anteriores.values())
    print(f"CONCLUÍDO relatório={args.saida} resumo={resumo} erros={erros}", flush=True)
    return 2 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
