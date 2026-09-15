import hashlib
import hmac
import os
import re
import unicodedata


HASH_DOCUMENTOS_VERSAO = 1


def normalizar_nome(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = re.sub(r"[^A-Za-z0-9 ]+", " ", texto.upper())
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_documento(valor: object) -> str:
    return "".join(caractere for caractere in str(valor or "") if caractere.isdigit())


def _segredo_documentos() -> bytes:
    # Chave própria, sem fallback para CRON_SECRET: são segredos com
    # propósitos diferentes (autenticação do cron vs. hash irreversível dos
    # documentos indexados). Reaproveitar o mesmo segredo para os dois faz
    # com que rotacionar o CRON_SECRET por qualquer motivo relacionado a ele
    # mude silenciosamente o hash de todo documento já indexado, tornando a
    # busca por CPF/CNPJ permanentemente muda sem reindexação.
    segredo = os.getenv("AERI_BUSCAS_HMAC_KEY")
    if not segredo or segredo == '[SENSITIVE]':
        raise RuntimeError("Configure AERI_BUSCAS_HMAC_KEY para proteger os documentos da busca.")
    return segredo.encode("utf-8")


def validar_configuracao_buscas() -> None:
    """Falha antes de consultar a Tri7 quando a chave do índice não existe."""
    if os.getenv('AERI_BUSCAS_HMAC_KEY') not in (None, '', '[SENSITIVE]'):
        _segredo_documentos()
    else:
        from backend.app.servicos.hash_remoto import verificar_servico
        verificar_servico()


def hash_documento(valor: object) -> str:
    return hash_documentos([valor])[0]


def hash_documentos(valores) -> list[str]:
    documentos = [normalizar_documento(v) for v in valores]
    validos = list(dict.fromkeys(d for d in documentos if len(d) in (11, 14)))
    if not validos:
        return ['' for _ in documentos]
    if os.getenv('AERI_BUSCAS_HMAC_KEY') not in (None, '', '[SENSITIVE]'):
        segredo = _segredo_documentos()
        hashes = [hmac.new(segredo, d.encode('ascii'), hashlib.sha256).hexdigest() for d in validos]
    else:
        from backend.app.servicos.hash_remoto import calcular_hashes
        hashes = calcular_hashes(validos)
    por_documento = dict(zip(validos, hashes))
    return [por_documento.get(d, '') for d in documentos]


def mascarar_documento(valor: object) -> str:
    documento = normalizar_documento(valor)
    if len(documento) == 11:
        return f"***.***.{documento[6:9]}-{documento[9:]}"
    if len(documento) == 14:
        return f"**.***.***/****-{documento[-2:]}"
    return ""


def tipo_documento(valor: object) -> str:
    tamanho = len(normalizar_documento(valor))
    return "CPF" if tamanho == 11 else "CNPJ" if tamanho == 14 else ""


def texto_hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def construir_indice_matricula(numero: int, texto: str, resultado: dict) -> dict:
    imovel = resultado.get("imovel") or {}
    situacao = imovel.get("situacao") or {}
    status = str(situacao.get("status") or "REVISAR").strip().upper()
    if status not in {"ATIVA", "ENCERRADA", "INEXISTENTE"}:
        status = "REVISAR"

    sucessoras = situacao.get("matriculas_sucessoras") or []
    if not sucessoras and situacao.get("matricula_sucessora"):
        sucessoras = [situacao["matricula_sucessora"]]

    evidencias = resultado.get("evidencias", {}).get("proprietarios", [])
    proprietarios = []
    titulares = resultado.get("proprietarios_atuais") or []
    hashes_titulares = hash_documentos(item.get('cpf') or '' for item in titulares)
    for ordem, item in enumerate(titulares, start=1):
        nome = re.sub(r"\s+", " ", str(item.get("nome") or "")).strip()
        nome_busca = normalizar_nome(nome)
        if not nome_busca:
            continue
        documento = item.get("cpf") or ""
        evidencia = evidencias[ordem - 1] if ordem <= len(evidencias) else {}
        documento_protegido = hashes_titulares[ordem-1]
        proprietarios.append({
            "ordem": ordem,
            "nome": nome,
            "nome_busca": nome_busca,
            "documento_hash": documento_protegido or None,
            "documento_mascarado": mascarar_documento(documento),
            "tipo_documento": tipo_documento(documento),
            "proporcao": str(item.get("proporcao") or "100%")[:40],
            "origem": str(evidencia.get("fonte") or "Cadeia dominial")[:80],
            "confianca": "ALTA" if documento_protegido else "MEDIA",
        })

    confianca = "ALTA" if proprietarios and all(
        item["confianca"] == "ALTA" for item in proprietarios
    ) else "MEDIA" if proprietarios else "BAIXA"
    meta = resultado.get("meta") or {}
    return {
        "numero": numero,
        "texto_hash": texto_hash(texto),
        "resultado_hash": resultado.get("resultado_hash"),
        "situacao": status,
        "situacao_origem": str(situacao.get("origem") or "Texto registral")[:120],
        "matriculas_sucessoras": [str(item)[:20] for item in sucessoras],
        "quantidade_proprietarios": len(proprietarios),
        "confianca": confianca,
        "motor_versao": str(meta.get("versao_indice") or meta.get("versao") or "")[:30],
        "proprietarios": proprietarios,
    }
