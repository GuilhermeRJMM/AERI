# Execute na máquina do executor, usando a chave JÁ EXISTENTE em produção.
# A entrada não é exibida nem colocada na linha de comando ou no histórico.
param([switch]$DaVercel, [string]$IdVariavel)
$ErrorActionPreference = 'Stop'
$raizBuscas = Split-Path -Parent $PSScriptRoot
$destinoBuscas = Join-Path $raizBuscas '.env.buscas.local'
if (Test-Path -LiteralPath $destinoBuscas) {
    throw 'O arquivo .env.buscas.local já existe. Confira a configuração existente antes de substituí-lo.'
}
if ($DaVercel) {
    if ($IdVariavel -notmatch '^[A-Za-z0-9_-]+$') { throw 'Informe o identificador exato da variável autorizada.' }
    $projeto = Get-Content -LiteralPath (Join-Path $raizBuscas '.vercel/project.json') -Raw | ConvertFrom-Json
    $endpoint = "/v1/projects/$($projeto.projectId)/env/$($IdVariavel)?teamId=$($projeto.orgId)"
    # Consulta uma única variável. A resposta permanece apenas na memória:
    # nunca escrever seu JSON, valor, stderr ou chave no console/log.
    $resposta = & npx --yes vercel api $endpoint --raw 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'A Vercel não liberou a leitura desta variável. Use o valor original manualmente.' }
    try { $variavel = $resposta | ConvertFrom-Json } catch { throw 'Resposta da Vercel inválida.' }
    $resposta = $null
    if ($variavel.key -ne 'AERI_BUSCAS_HMAC_KEY' -or !$variavel.value -or $variavel.value -eq '[SENSITIVE]') {
        throw 'Chave sensível não recuperável. Use o valor original manualmente; não gere outra chave.'
    }
    $segredoBuscas = ConvertTo-SecureString -String $variavel.value -AsPlainText -Force
    $variavel = $null
} else {
    $segredoBuscas = Read-Host 'Cole a chave AERI_BUSCAS_HMAC_KEY existente no AERI (não crie outra)' -AsSecureString
}
$ponteiroBuscas = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segredoBuscas)
try {
    $valorBuscas = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ponteiroBuscas)
    if ($valorBuscas.Length -lt 16 -or $valorBuscas -match '[\r\n]' -or $valorBuscas -match '\[SENSITIVE\]') {
        throw 'Chave inválida. Informe o valor original, completo.'
    }
    [IO.File]::WriteAllText($destinoBuscas, "AERI_BUSCAS_HMAC_KEY=$valorBuscas`n", [Text.UTF8Encoding]::new($false))
    Write-Host 'Chave salva em arquivo ignorado pelo Git. Reinicie o executor para carregar a configuração.'
} finally {
    $valorBuscas = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ponteiroBuscas)
    $segredoBuscas.Dispose()
}
