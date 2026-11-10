"""DPAPI do usuário Windows: não persiste credencial em texto puro."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


class Blob(ctypes.Structure):
    _fields_ = [('tamanho',wintypes.DWORD),('dados',ctypes.POINTER(ctypes.c_byte))]


def proteger(dados, *, abrir=False):
    if os.name != 'nt':
        raise RuntimeError('Este conector requer Windows com DPAPI.')
    crypt = ctypes.WinDLL('crypt32',use_last_error=True)
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    entrada_buffer=ctypes.create_string_buffer(dados)
    entrada=Blob(len(dados),ctypes.cast(entrada_buffer,ctypes.POINTER(ctypes.c_byte)))
    saida=Blob()
    if abrir:
        ok=crypt.CryptUnprotectData(ctypes.byref(entrada),None,None,None,None,1,ctypes.byref(saida))
    else:
        ok=crypt.CryptProtectData(ctypes.byref(entrada),None,None,None,None,1,ctypes.byref(saida))
    if not ok:
        raise RuntimeError('Não foi possível proteger/abrir a credencial deste usuário Windows.')
    try:
        return ctypes.string_at(saida.dados,saida.tamanho)
    finally:
        kernel.LocalFree.argtypes=[ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(saida.dados,ctypes.c_void_p))


def caminho():
    return Path(os.environ['LOCALAPPDATA'])/'AnalisadorRGI-Lab'/'oficio-conector.dpapi'


def salvar(dados):
    destino=caminho()
    destino.parent.mkdir(parents=True,exist_ok=True)
    destino.write_bytes(proteger(json.dumps(dados).encode('utf-8')))


def carregar():
    return json.loads(proteger(caminho().read_bytes(),abrir=True))
