"""Identidade e padrões de busca, sem acesso a banco ou dados operacionais."""
import re
import unicodedata


def escapar_like(valor: str) -> str:
    """Caracteres digitados são literais; nunca curingas de uma consulta LIKE."""
    return valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def documento_da_consulta(valor: str) -> str | None:
    """Somente uma entrada documental, nunca dígitos extraídos de uma empresa."""
    if any(c.isalpha() for c in valor):
        return None
    digitos = "".join(c for c in valor if c.isdigit())
    if digitos and len(digitos) not in {11, 14}:
        raise ValueError("Informe o CPF ou CNPJ completo.")
    return digitos or None


def chave_nome(valor: str) -> tuple[str, ...]:
    texto = "".join(c for c in unicodedata.normalize("NFKD", valor or "")
                    if not unicodedata.combining(c)).upper()
    return tuple(sorted(p for p in re.findall(r"\w+", texto)
                        if p not in {"DA", "DE", "DO", "DAS", "DOS", "E"}))


def nomes_equivalentes(a: str, b: str) -> bool:
    chave = chave_nome(a)
    return bool(chave and chave == chave_nome(b))
