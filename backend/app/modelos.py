from pydantic import BaseModel


class Ato(BaseModel):

    codigo: str

    descricao: str

    categoria: str = "DESCONHECIDO"

    status: str = "ATIVO"

    cancelado_por: str | None = None

    impacta_resultado: bool = False