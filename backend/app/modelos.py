from typing import Optional
from pydantic import BaseModel

class Ato(BaseModel):
    codigo: str
    descricao: str
    categoria: str = "DESCONHECIDO"
    status: str = "ATIVO"
    
    # O Vercel (Python 3.9) exige 'Optional' em vez de 'str | None'
    cancelado_por: Optional[str] = None
    
    impacta_resultado: bool = False