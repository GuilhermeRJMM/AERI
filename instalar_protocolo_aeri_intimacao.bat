@echo off
setlocal
set "RAIZ=%~dp0"
set "SCRIPT=%RAIZ%ferramentas\abrir_pasta_intimacao.py"

if not exist "%SCRIPT%" (
  echo O programa local de intimacoes nao foi encontrado:
  echo %SCRIPT%
  pause
  exit /b 1
)

set "PYTHONW="
for /f "delims=" %%P in ('where pythonw 2^>nul') do if not defined PYTHONW set "PYTHONW=%%P"
if not defined PYTHONW (
  echo Python nao foi localizado neste computador.
  pause
  exit /b 1
)

reg add "HKCU\Software\Classes\aeri-intimacao" /ve /d "URL:AERI Intimacao" /f
reg add "HKCU\Software\Classes\aeri-intimacao" /v "URL Protocol" /d "" /f
reg add "HKCU\Software\Classes\aeri-intimacao\shell\open\command" /ve /d "\"%PYTHONW%\" \"%SCRIPT%\" \"%%1\"" /f

echo.
echo Protocolo aeri-intimacao instalado com sucesso.
echo Abrir pasta e copiar o caminho nao dependem da biblioteca pypdf.
echo Para gerar a nota de Desistencia, instale as dependencias do AERI.
echo Agora o AERI pode abrir pastas usando links aeri-intimacao://abrir/IN00000000C
echo E pode gerar notas usando links aeri-intimacao://gerar-desistencia/IN00000000C
echo.
pause
