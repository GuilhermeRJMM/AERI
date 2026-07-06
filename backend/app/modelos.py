from typing import Optional
from pydantic import BaseModel, Field

class Ato(BaseModel):
    codigo: str
    descricao: str
    categoria: str = "DESCONHECIDO"
    status: str = "ATIVO"
    
    # O Vercel (Python 3.9) exige 'Optional' em vez de 'str | None'
    cancelado_por: Optional[str] = None
    cancela_atos: list[str] = Field(default_factory=list)
    
    impacta_resultado: bool = False
