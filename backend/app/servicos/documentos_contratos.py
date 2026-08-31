"""Extração por página, com OCR local automático e preservação do texto original."""
import csv
import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LIMITE_PAGINAS = 100


class DocumentoInvalido(ValueError):
    pass


class OcrIndisponivel(RuntimeError):
    pass


def texto_suficiente(texto):
    letras = sum(c.isalnum() for c in texto)
    return letras >= 160 and texto.count("�") <= max(2, len(texto) // 100)


def normalizar_texto(texto):
    # Não troca O/0, I/1, valores, documentos ou datas silenciosamente.
    return "\n".join(re.sub(r"[ \t]+", " ", linha).strip() for linha in texto.replace("\r", "").splitlines()).strip()


def reconhecer_png(png):
    with tempfile.TemporaryDirectory(prefix="aeri-ocr-") as pasta:
        caminho = Path(pasta) / "p001.png"
        caminho.write_bytes(png)
        tesseract = os.getenv("TESSERACT_EXE") or shutil.which("tesseract")
        windows = Path(__file__).resolve().parents[3] / "scripts" / "ocr_windows_contratos.ps1"
        if os.name == "nt" and windows.exists() and shutil.which("powershell"):
            proc = subprocess.run(["powershell", "-NoProfile", "-File", str(windows), "-Pasta", pasta,
                                   "-Idioma", "pt-BR"], capture_output=True, timeout=90,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if proc.returncode == 0:
                texto = re.sub(r"^@@PAGINA.*$", "", proc.stdout.decode("utf-8", "replace"), flags=re.M).strip()
                if texto:
                    return texto, "OCR Windows", None
        if not tesseract:
            raise OcrIndisponivel("Documento digitalizado: configure OCR Windows pt-BR ou Tesseract com idioma português no worker.")
        proc = subprocess.run([tesseract, str(caminho), "stdout", "-l", "por", "tsv"],
                              capture_output=True, timeout=90,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode:
            raise OcrIndisponivel("Falha no OCR. Verifique o idioma português no worker.")
        linhas, confiancas = {}, []
        for r in csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", "replace")), delimiter="\t"):
            palavra = r.get("text", "").strip()
            if not palavra:
                continue
            chave = (r.get("block_num"), r.get("par_num"), r.get("line_num"))
            linhas.setdefault(chave, []).append(palavra)
            try:
                c = float(r.get("conf", -1))
                if c >= 0:
                    confiancas.append(c)
            except ValueError:
                pass
        return "\n".join(" ".join(l) for l in linhas.values()), "OCR Tesseract", min(confiancas) if confiancas else None


def extrair_documento(dados: bytes, progresso=None):
    import pymupdf
    if not dados or len(dados) > 60_000_000:
        raise DocumentoInvalido("Documento vazio ou superior a 60 MB.")
    pdf = None
    try:
        if dados.startswith(b"%PDF"):
            pdf = pymupdf.open(stream=dados, filetype="pdf")
            if pdf.needs_pass:
                raise DocumentoInvalido("O PDF está protegido por senha.")
        else:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = 20_000_000
            imagem = Image.open(io.BytesIO(dados))
            if imagem.format not in {"JPEG", "PNG", "TIFF"}:
                raise DocumentoInvalido("Use PDF, JPEG, PNG ou TIFF.")
            if getattr(imagem, "n_frames", 1) > LIMITE_PAGINAS:
                raise DocumentoInvalido("Documento excede 100 páginas.")
            pdf = pymupdf.open()
            for i in range(getattr(imagem, "n_frames", 1)):
                imagem.seek(i)
                if imagem.width * imagem.height > 20_000_000:
                    raise DocumentoInvalido("Imagem excede a resolução permitida.")
                buffer = io.BytesIO()
                imagem.convert("RGB").save(buffer, format="PNG")
                pagina = pdf.new_page(width=595, height=595 * imagem.height / imagem.width)
                pagina.insert_image(pagina.rect, stream=buffer.getvalue())
        if not 1 <= len(pdf) <= LIMITE_PAGINAS:
            raise DocumentoInvalido("Documento precisa ter entre 1 e 100 páginas.")
        paginas = []
        for i, pagina in enumerate(pdf):
            texto = pagina.get_text(sort=True)
            original = texto
            metodo, confianca = "Texto digital", None
            if not texto_suficiente(texto) and (pagina.get_images() or texto.strip() or not dados.startswith(b"%PDF")):
                escala = min(3, 2400 / max(pagina.rect.width, 1), (12_000_000 / max(pagina.rect.width*pagina.rect.height, 1)) ** .5)
                png = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False).tobytes("png")
                texto, metodo, confianca = reconhecer_png(png)
            paginas.append({"pagina": i+1, "textoOriginal": original, "texto": normalizar_texto(texto),
                            "metodo": metodo, "confianca": confianca, "insuficiente": not texto_suficiente(texto)})
            if progresso:
                progresso(i+1, len(pdf))
        if not any(texto_suficiente(p["texto"]) for p in paginas):
            raise DocumentoInvalido("Não foi possível extrair texto suficiente. Confira a qualidade do documento.")
        return {"sha256": hashlib.sha256(dados).hexdigest(), "paginas": paginas,
                "texto": "\n\n".join(p["texto"] for p in paginas), "ocr": any(p["metodo"].startswith("OCR") for p in paginas)}
    except (DocumentoInvalido, OcrIndisponivel):
        raise
    except Exception as exc:
        raise DocumentoInvalido("Não foi possível ler o arquivo; ele pode estar corrompido ou fora dos formatos aceitos.") from exc
    finally:
        if pdf is not None:
            pdf.close()
