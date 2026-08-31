"""Leitura do PDF.

Duas naturezas chegam à serventia e o sistema decide sozinho qual é:

- **nato-digital** — tem camada de texto; o extrator lê por rótulo, e é
  confiável. A cláusula 33 do próprio contrato prevê essa via.
- **digitalizado** — imagem pura; sem OCR não há texto, e a página é
  rasterizada para o conferente ler na tela, ao lado do campo.

O corte é grosseiro de propósito: uma página de contrato tem centenas de
caracteres, e um PDF digitalizado devolve quase zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

CARACTERES_POR_PAGINA_MINIMO = 200


# Fração da página que uma imagem precisa cobrir para a página ser considerada
# uma fotografia. Um contrato nato-digital tem no máximo o logotipo da CAIXA,
# que ocupa muito menos que isso.
COBERTURA_DE_IMAGEM = 0.55


@dataclass
class Documento:
    caminho: Path
    paginas: int
    texto: str
    nato_digital: bool
    eh_foto: bool = False
    tem_camada_de_texto: bool = False

    @property
    def caracteres_por_pagina(self) -> float:
        return len(self.texto) / self.paginas if self.paginas else 0.0


def _pagina_e_foto(pagina) -> bool:
    """A página é a fotografia de um papel?

    Contar caracteres não basta: um PDF escaneado pode vir com camada de texto
    embutida pelo programa do scanner, e essa camada é de OCR — de qualidade
    desconhecida, feita por outro motor, sem ninguém ter conferido. Passa pelo
    teste de "tem texto" e não devia.

    O que distingue de verdade é a imagem: papel fotografado tem uma imagem
    cobrindo a página inteira; contrato nato-digital não tem.
    """
    area = pagina.rect.get_area()
    if not area:
        return False
    for info in pagina.get_image_info():
        if pymupdf.Rect(info["bbox"]).get_area() >= COBERTURA_DE_IMAGEM * area:
            return True
    return False


def abre(caminho) -> Documento:
    caminho = Path(caminho)
    with pymupdf.open(caminho) as pdf:
        paginas = pdf.page_count
        partes = []
        fotos = 0
        for pagina in pdf:
            partes.append(pagina.get_text())
            if _pagina_e_foto(pagina):
                fotos += 1

    texto = "\n".join(partes)
    tem_texto = paginas > 0 and (len(texto) / paginas) >= CARACTERES_POR_PAGINA_MINIMO
    # Maioria das páginas fotografada: o documento é digitalização.
    eh_foto = paginas > 0 and fotos >= paginas / 2

    return Documento(caminho=caminho, paginas=paginas, texto=texto,
                     nato_digital=tem_texto and not eh_foto,
                     eh_foto=eh_foto, tem_camada_de_texto=tem_texto)


def largura_nativa(caminho, indice_pagina: int) -> int:
    """Largura, em pixels, da maior imagem embutida na página.

    Rasterizar abaixo disso joga fora detalhe que o scanner capturou, e o OCR
    paga o preço. Medido no acervo: as imagens vão de 2416 a 4816px de largura,
    e a rasterização fixa em 2200px descartava mais da metade da informação nos
    documentos maiores.
    """
    with pymupdf.open(caminho) as pdf:
        pagina = pdf[indice_pagina]
        larguras = [info["width"] for info in pagina.get_image_info()]
    return max(larguras) if larguras else 0


def renderiza(caminho, indice_pagina: int, largura: int = 1700) -> bytes:
    """PNG de uma página, para o conferente ver a caixa de onde o campo saiu.

    Serve tanto ao digitalizado (é a única leitura possível) quanto ao
    nato-digital (mostrar a origem é o que torna a conferência real)."""
    with pymupdf.open(caminho) as pdf:
        pagina = pdf[indice_pagina]
        escala = largura / pagina.rect.width
        pixmap = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala))
        return pixmap.tobytes("png")


def texto_por_pagina(caminho) -> list[str]:
    with pymupdf.open(caminho) as pdf:
        return [pagina.get_text() for pagina in pdf]
