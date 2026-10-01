param([switch]$Remover,[switch]$Reiniciar)
$ErrorActionPreference='Stop'
$Nome='AERI RTD'
$Raiz=Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($Remover) {
    Stop-ScheduledTask -TaskName $Nome -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $Nome -Confirm:$false
    return
}
if ($Reiniciar) {
    Stop-ScheduledTask -TaskName $Nome -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $Nome
    return
}
if (-not (Test-Path -LiteralPath (Join-Path $Raiz '.env.rtd.local'))) { throw 'Configure a chave com scripts/sincronizar_rtd.py --configurar antes de instalar.' }
$Python=(& python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Python)) { throw 'Python indisponível.' }
$Pythonw=Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $Pythonw)) { throw 'pythonw.exe não localizado; não iniciar janela visível.' }
$Script=Join-Path $Raiz 'scripts\worker_rtd.py'
$Acao=New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Script`"" -WorkingDirectory $Raiz
$Gatilho=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Config=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3
$Config.ExecutionTimeLimit='PT0S'
Register-ScheduledTask -TaskName $Nome -Action $Acao -Trigger $Gatilho -Settings $Config -Description 'Acompanha diligências RTD e vincula às intimações AERI; somente leitura na central.' -Force | Out-Null
Start-ScheduledTask -TaskName $Nome
Get-ScheduledTask -TaskName $Nome | Select-Object TaskName,State
