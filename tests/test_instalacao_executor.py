"""Instalação local não herda a identidade da Vercel nem usa Python sem dependências."""
from pathlib import Path
from scripts.worker_operacional import carregar_env


def test_env_importado_da_vercel_nao_impede_hash_remoto(tmp_path, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("AERI_TESTE_LOCAL", raising=False)
    arquivo = tmp_path / ".env"
    arquivo.write_text("VERCEL=1\nVERCEL_ENV=production\nAERI_TESTE_LOCAL=ok\n", encoding="utf-8")
    carregar_env(arquivo)
    import os
    assert "VERCEL" not in os.environ
    assert "VERCEL_ENV" not in os.environ
    assert os.environ["AERI_TESTE_LOCAL"] == "ok"
    monkeypatch.delenv("AERI_TESTE_LOCAL")


def test_ambiente_real_nao_e_rebaixado_por_arquivo(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    arquivo = tmp_path / ".env"
    arquivo.write_text("VERCEL=0\n", encoding="utf-8")
    carregar_env(arquivo)
    import os
    assert os.environ["VERCEL"] == "1"


def test_instalador_prefere_python_do_ambiente_privado():
    texto = (Path(__file__).parents[1] / "scripts/instalar_executor.ps1").read_text(encoding="utf-8")
    assert "PythonExecutavel" in texto
    assert ".venv\\Scripts\\python.exe" in texto
