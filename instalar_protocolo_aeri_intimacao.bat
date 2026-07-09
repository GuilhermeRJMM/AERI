@echo off
setlocal
set "RAIZ=%~dp0"
set "SCRIPT=%RAIZ%ferramentas\abrir_pasta_intimacao.py"

reg add "HKCU\Software\Classes\aeri-intimacao" /ve /d "URL:AERI Intimacao" /f
reg add "HKCU\Software\Classes\aeri-intimacao" /v "URL Protocol" /d "" /f
reg add "HKCU\Software\Classes\aeri-intimacao\shell\open\command" /ve /d "\"pythonw\" \"%SCRIPT%\" \"%%1\"" /f

echo.
echo Protocolo aeri-intimacao instalado com sucesso.
echo Agora o AERI pode abrir pastas usando links aeri-intimacao://abrir/IN00000000C
echo.
pause
