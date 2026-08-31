# OCR com o motor do proprio Windows (Windows.Media.Ocr).
#
# Recebe uma pasta com PNGs e devolve o texto de cada um, separado por
# marcadores de pagina. Nao instala nada e nao manda o arquivo para lugar
# nenhum: o reconhecimento acontece nesta maquina, o que e a condicao para
# poder usar isto com contrato de cliente.
#
#   powershell -File tools/ocr_windows.ps1 -Pasta C:\temp\paginas -Idioma pt-BR
param(
  [Parameter(Mandatory = $true)][string]$Pasta,
  [string]$Idioma = "pt-BR"
)

$ErrorActionPreference = "Stop"

# Sem isto o PowerShell escreve a saida no code page do console, e todo acento
# vira caractere de substituicao ao ser lido do outro lado do cano. O texto
# chega legivel mas com "cl?usula" no lugar de "clausula" acentuada, e a
# extracao por rotulo para de casar sem dizer por que.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# WinRT devolve IAsyncOperation<T> e IAsyncAction, que precisam de helpers
# diferentes para virar Task. Sem os dois, metade das chamadas nao espera.
$extensoes = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTaskGenerico = ($extensoes | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Aguarda($operacao, $tipo) {
  $tarefa = $asTaskGenerico.MakeGenericMethod($tipo).Invoke($null, @($operacao))
  $tarefa.Wait(-1) | Out-Null
  $tarefa.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

$lingua = New-Object Windows.Globalization.Language $Idioma
$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lingua)
if ($null -eq $motor) {
  Write-Error "o Windows nao tem o pacote de OCR para $Idioma instalado."
  exit 2
}

foreach ($png in (Get-ChildItem -Path $Pasta -Filter *.png | Sort-Object Name)) {
  $arquivo = Aguarda ([Windows.Storage.StorageFile]::GetFileFromPathAsync($png.FullName)) ([Windows.Storage.StorageFile])
  $fluxo = Aguarda ($arquivo.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  try {
    $decodificador = Aguarda ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($fluxo)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $imagem = Aguarda ($decodificador.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $resultado = Aguarda ($motor.RecognizeAsync($imagem)) ([Windows.Media.Ocr.OcrResult])

    Write-Output ("@@PAGINA " + $png.BaseName)
    # RecognizeAsync devolve o texto todo numa linha so; as linhas do
    # reconhecimento preservam a quebra do documento, e a leitura por rotulo
    # depende disso.
    foreach ($linha in $resultado.Lines) { Write-Output $linha.Text }
  }
  finally {
    $fluxo.Dispose()
  }
}
