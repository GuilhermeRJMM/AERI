"""Conciliação Tri7 compartilhada pela conferência manual e pelo executor automático."""
from backend.app.servicos.tri7 import ErroTri7, ProtocoloTri7NaoEncontrado
from backend.app.servicos.livro_protocolos import (
    referencias_textos_protocolo, registros_alterados_no_protocolo,
    codigos_atos_confirmados, conferir_protocolo,
)


def conferir_itens_tri7(itens, data_esperada, excecoes, cliente):
    cache_textos: dict[tuple[str, int], tuple[str | None, str | None]] = {}
    cache_atos: dict[tuple[str, int], set[tuple[str, int]]] = {}
    alterados: set[tuple[str, int]] = set()
    resultados = []
    for item in itens:
        registro = {**item, "conferido": False, "ocorrencias": [], "erro": None}
        if item["status"] == "REGISTRADO":
            try:
                protocolo_json = cliente.buscar_protocolo_completo(item["numero"])
                alterados |= registros_alterados_no_protocolo(protocolo_json)
                textos_registros = {}
                falhas_textos = {}
                atos_confirmados = {}
                for referencia in referencias_textos_protocolo(protocolo_json):
                    if referencia not in cache_textos:
                        try:
                            if referencia[0] == "M":
                                resposta_texto = cliente.buscar_texto_matricula(referencia[1])
                            else:
                                resposta_texto = cliente.buscar_texto_registro_auxiliar(referencia[1])
                            cache_textos[referencia] = (resposta_texto["texto"], None)
                        except ErroTri7 as erro:
                            cache_textos[referencia] = (None, str(erro))
                    texto, falha = cache_textos[referencia]
                    if texto:
                        textos_registros[referencia] = texto
                    elif falha:
                        falhas_textos[referencia] = falha
                    if referencia[0] == "M":
                        if referencia not in cache_atos:
                            try:
                                cache_atos[referencia] = codigos_atos_confirmados(
                                    cliente.buscar_atos_matricula(referencia[1])
                                )
                            except ErroTri7:
                                # O endpoint complementar não é condição para
                                # conferir o livro: em falha, preserva-se a
                                # validação anterior baseada no texto.
                                cache_atos[referencia] = set()
                        atos_confirmados[referencia] = cache_atos[referencia]
                registro["ocorrencias"] = conferir_protocolo(
                    item, protocolo_json, data_esperada, excecoes,
                    textos_registros=textos_registros,
                    falhas_textos=falhas_textos,
                    atos_confirmados=atos_confirmados,
                )
                registro["conferido"] = True
            except ProtocoloTri7NaoEncontrado:
                registro["erro"] = "Protocolo não encontrado na Tri7."
            except ErroTri7 as erro:
                registro["erro"] = str(erro)
        resultados.append(registro)

    return resultados, alterados, cache_textos
