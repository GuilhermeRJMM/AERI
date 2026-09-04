"""O motor de OCR que não se instala precisa estar ao alcance do código.

O script do Windows.Media.Ocr é a dependência de runtime do pacote
contratos_nucleo, não um utilitário de operador: ele mora junto do código que o
executa. Já esteve em scripts/ com outro nome, e o efeito era silencioso --
motor() devolvia None, disponivel() era False e o sistema dizia que precisava
de OCR "não ativado", quando o motor estava no sistema operacional o tempo
todo. Só o Tesseract, que exige instalação, salvaria o caso.
"""
import sys
import unittest
from pathlib import Path

from backend.app.contratos_nucleo import ocr


class TesteMotorDeOcr(unittest.TestCase):
    def test_script_do_windows_esta_onde_o_codigo_procura(self):
        self.assertTrue(
            ocr.SCRIPT_WINDOWS.exists(),
            f"o script do OCR do Windows precisa estar em {ocr.SCRIPT_WINDOWS}",
        )

    def test_script_aceita_os_parametros_que_o_codigo_passa(self):
        fonte = ocr.SCRIPT_WINDOWS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("$Pasta", fonte)
        self.assertIn("$Idioma", fonte)
        # O Python remove estes marcadores da saida; sem eles as paginas se
        # emendam e o rotulo da caixa seguinte gruda no texto da anterior.
        self.assertIn("@@PAGINA", fonte)

    def test_nao_ha_copia_orfa_do_script_em_scripts(self):
        raiz = Path(__file__).resolve().parents[1]
        orfaos = list((raiz / "scripts").glob("ocr_windows*.ps1"))
        self.assertEqual(orfaos, [], "duas cópias divergem; a que vale mora junto do código")

    @unittest.skipUnless(sys.platform == "win32", "o OCR local só existe no Windows")
    def test_no_windows_o_motor_padrao_dispensa_instalacao(self):
        # A ordem e por medicao, nao preferencia: o motor do Windows ganhou do
        # Tesseract em todas as configuracoes testadas (ver docstring de motor()).
        self.assertTrue(ocr.disponivel(), "com PowerShell e o script no lugar, tem de haver motor")
        self.assertEqual(ocr.motor(), "windows")

    def test_fora_do_windows_o_sistema_admite_que_nao_tem_motor(self):
        # Na Vercel nao ha OCR local: dizer que o contrato e digitalizado e
        # correto; fingir que leu seria pior.
        if sys.platform != "win32":
            self.assertIsNone(ocr.motor())
            self.assertFalse(ocr.disponivel())

    def test_correcao_recupera_os_rotulos_das_caixas(self):
        # Erros medidos no motor do Windows: "A1" -> "Al", "B10.1" -> "BIO.I".
        # Sao os mais caros, porque a extracao inteira ancora no rotulo.
        corrigido = ocr.corrige("Al - QUALIFICACAO DAS PARTES\nBIO.I - VALOR DO FINANCIAMENTO")
        self.assertIn("A1 - QUALIFICACAO", corrigido)
        self.assertIn("B10.1 - VALOR", corrigido)


if __name__ == "__main__":
    unittest.main()


class TesteExecutorOperacional(unittest.TestCase):
    """O executor roda numa máquina da serventia, a partir do repositório.

    Sem carregar o .env ele morria em "DATABASE_URL ausente" com traceback,
    antes de qualquer diagnóstico -- e nada no projeto carregava esse arquivo,
    porque o app roda na Vercel, onde as variáveis vêm do painel.
    """

    def _worker(self):
        import importlib.util
        raiz = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "worker_operacional", raiz / "scripts" / "worker_operacional.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo

    def test_carrega_env_sem_sobrescrever_o_ambiente(self):
        import os
        import tempfile
        worker = self._worker()
        pasta = Path(tempfile.mkdtemp())
        (pasta / ".env").write_text(
            '# comentario\nAERI_TESTE_NOVA=doArquivo\nAERI_TESTE_EXISTENTE="doArquivo"\n\n',
            encoding="utf-8")
        os.environ.pop("AERI_TESTE_NOVA", None)
        os.environ["AERI_TESTE_EXISTENTE"] = "doSistema"
        try:
            worker.carregar_env(pasta / ".env")
            self.assertEqual(os.environ["AERI_TESTE_NOVA"], "doArquivo")
            # Quem opera a maquina manda: variavel ja definida vence o arquivo.
            self.assertEqual(os.environ["AERI_TESTE_EXISTENTE"], "doSistema")
        finally:
            os.environ.pop("AERI_TESTE_NOVA", None)
            os.environ.pop("AERI_TESTE_EXISTENTE", None)

    def test_arquivo_ausente_nao_quebra(self):
        worker = self._worker()
        worker.carregar_env(Path("nao-existe-em-lugar-nenhum.env"))

    def test_sem_configuracao_diz_o_que_falta_e_sai_com_erro(self):
        from unittest.mock import patch
        worker = self._worker()
        with patch.dict("os.environ", {}, clear=True), \
             patch.object(worker, "carregar_env"), \
             patch.object(worker, "preparar_banco") as preparar, \
             patch("sys.argv", ["worker", "--once"]), \
             self.assertLogs(level="ERROR") as registro:
            self.assertEqual(worker.main(), 1)
        preparar.assert_not_called()
        aviso = " ".join(registro.output)
        self.assertIn("POSTGRES_URL", aviso)
        self.assertIn("AERI_CONTRATOS_ENCRYPTION_KEY", aviso)

    def test_aceita_os_mesmos_nomes_que_o_codigo_le(self):
        """database.py aceita POSTGRES_URL ou DATABASE_URL; cifrador() aceita a
        chave dos contratos ou a das buscas. Exigir um nome so reprovaria
        maquina bem configurada."""
        from unittest.mock import patch
        worker = self._worker()
        for banco in ("POSTGRES_URL", "DATABASE_URL"):
            for chave in ("AERI_CONTRATOS_ENCRYPTION_KEY", "AERI_BUSCAS_HMAC_KEY"):
                with self.subTest(banco=banco, chave=chave):
                    ambiente = {banco: "postgres://teste", chave: "x" * 40}
                    with patch.dict("os.environ", ambiente, clear=True),                          patch.object(worker, "carregar_env"),                          patch.object(worker, "preparar_banco") as preparar,                          patch.object(worker, "executar_passo", return_value={"estado": "OK"}),                          patch.object(worker, "processar_proximo_contrato",
                                      return_value={"estado": "SEM_TRABALHO"}),                          patch("sys.argv", ["worker", "--once"]):
                        self.assertEqual(worker.main(), 0)
                    preparar.assert_called_once()

    def test_placeholder_do_vercel_conta_como_ausente(self):
        """`vercel env pull` grava "[SENSITIVE]" para variavel secreta.

        Aceitar esse texto trocava o aviso do que falta por um erro de conexao
        do driver, que nao diz o que fazer.
        """
        import os
        import tempfile
        worker = self._worker()
        pasta = Path(tempfile.mkdtemp())
        (pasta / ".env").write_text(
            'POSTGRES_URL="[SENSITIVE]"\nAERI_TESTE_VAZIO=\nAERI_TESTE_BOM=valor\n',
            encoding="utf-8")
        for chave in ("POSTGRES_URL", "AERI_TESTE_VAZIO", "AERI_TESTE_BOM"):
            os.environ.pop(chave, None)
        try:
            worker.carregar_env(pasta / ".env")
            self.assertNotIn("POSTGRES_URL", os.environ)
            self.assertNotIn("AERI_TESTE_VAZIO", os.environ)
            self.assertEqual(os.environ["AERI_TESTE_BOM"], "valor")
        finally:
            for chave in ("POSTGRES_URL", "AERI_TESTE_VAZIO", "AERI_TESTE_BOM"):
                os.environ.pop(chave, None)

    def test_encerra_o_pool_no_fim_do_ciclo(self):
        """Sem fechar, o __del__ do psycopg_pool tenta juntar threads durante o
        encerramento do interpretador e o Python levanta PythonFinalizationError:
        um traceback de quatro linhas depois de um ciclo bem-sucedido."""
        from unittest.mock import patch
        worker = self._worker()
        ambiente = {"POSTGRES_URL": "postgres://teste", "AERI_BUSCAS_HMAC_KEY": "x" * 40}
        with patch.dict("os.environ", ambiente, clear=True), \
             patch.object(worker, "carregar_env"), \
             patch.object(worker, "preparar_banco"), \
             patch.object(worker, "executar_passo", return_value={"estado": "OK"}), \
             patch.object(worker, "processar_proximo_contrato", return_value={"estado": "SEM_TRABALHO"}), \
             patch.object(worker, "fechar_pool") as fechar, \
             patch("sys.argv", ["worker", "--once"]):
            self.assertEqual(worker.main(), 0)
        fechar.assert_called_once()


class TestePoolDoBanco(unittest.TestCase):
    def test_fechar_pool_libera_e_pode_ser_chamado_duas_vezes(self):
        from unittest.mock import MagicMock, patch
        from backend.app import database
        falso = MagicMock()
        with patch.object(database, "_pool", falso):
            database.fechar_pool()
            falso.close.assert_called_once()
            self.assertIsNone(database._pool)
            database.fechar_pool()  # idempotente: servico reinicia sem estourar


class TesteInstaladorDoExecutor(unittest.TestCase):
    """O executor precisa rodar sozinho: ninguém vai abrir terminal a cada
    contrato digitalizado."""

    def _script(self):
        return Path(__file__).resolve().parents[1] / "scripts" / "instalar_executor.ps1"

    def test_instalador_existe_e_aponta_para_o_worker(self):
        fonte = self._script().read_text(encoding="utf-8", errors="replace")
        self.assertIn("worker_operacional.py", fonte)
        self.assertIn("Register-ScheduledTask", fonte)
        self.assertIn("-Remover", fonte, "precisa ter como desinstalar")

    def test_usa_pythonw_para_nao_piscar_console(self):
        fonte = self._script().read_text(encoding="utf-8", errors="replace")
        self.assertIn("pythonw.exe", fonte)

    def test_recusa_instalar_sem_env_configurado(self):
        # Instalar uma tarefa que so vai falhar em silencio e pior que nao
        # instalar: o conferente acha que esta funcionando.
        fonte = self._script().read_text(encoding="utf-8", errors="replace")
        self.assertIn('Test-Path (Join-Path $Raiz ".env")', fonte)

    def test_worker_registra_em_arquivo(self):
        """Por pythonw nao ha console: sem arquivo, o processo fica invisivel."""
        fonte = (Path(__file__).resolve().parents[1] / "scripts" / "worker_operacional.py") \
            .read_text(encoding="utf-8", errors="replace")
        self.assertIn("RotatingFileHandler", fonte)
        self.assertIn("executor.log", fonte)

    def test_nenhum_subprocesso_abre_console(self):
        """Rodando pelo executor, cada janela aparece na cara do conferente.

        Um contrato de 24 paginas chegou a piscar 24 consoles de PowerShell.
        """
        import re
        for arquivo in ("backend/app/contratos_nucleo/ocr.py",
                        "backend/app/servicos/documentos_contratos.py"):
            fonte = (Path(__file__).resolve().parents[1] / arquivo).read_text(encoding="utf-8")
            chamadas = len(re.findall(r"subprocess\.run\(", fonte))
            protegidas = len(re.findall(r"CREATE_NO_WINDOW", fonte))
            self.assertEqual(protegidas, chamadas,
                             f"{arquivo}: {chamadas} subprocess.run e {protegidas} protegidos")

    def test_instalador_tem_como_reiniciar(self):
        """Python importa os modulos uma vez: um executor ja rodando segue com o
        codigo velho depois de um git pull. Foi assim que uma correcao ficou 24
        minutos sem efeito enquanto o processo antigo abria consoles."""
        fonte = self._script().read_text(encoding="utf-8", errors="replace")
        self.assertIn("-Reiniciar", fonte)
        self.assertIn("Stop-ScheduledTask", fonte)

    def test_log_diz_de_quando_e_o_codigo_carregado(self):
        fonte = (Path(__file__).resolve().parents[1] / "scripts" / "worker_operacional.py") \
            .read_text(encoding="utf-8", errors="replace")
        self.assertIn("codigo_de", fonte,
                      "sem isso nao da para saber, pelo log, se o executor pegou a correcao")
