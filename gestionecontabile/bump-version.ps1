# Allinea la versione tra config.yaml (letto da Home Assistant) e
# frontend/package.json (mostrata nel footer della sidebar dell'app) in un
# solo comando, cosi' non si dimentica di aggiornarne uno dei due.

param(
    [Parameter(Position = 0)]
    [ValidateSet('patch', 'minor', 'major')]
    [string]$Bump = 'patch',

    [string]$Version   # se indicato, usa questo valore esatto invece di calcolarlo da -Bump
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$configPath  = Join-Path $root 'config.yaml'
$pkgPath     = Join-Path $root 'frontend/package.json'

$configContent = Get-Content $configPath -Raw
if ($configContent -notmatch 'version:\s*"(?<version>\d+\.\d+\.\d+)"') {
    throw "Impossibile trovare 'version: `"X.Y.Z`"' in $configPath"
}
$currentVersion = $Matches.version

if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Formato versione non valido: '$Version' (atteso X.Y.Z)" }
    $newVersion = $Version
} else {
    $parts = $currentVersion.Split('.') | ForEach-Object { [int]$_ }
    switch ($Bump) {
        'major' { $parts[0]++; $parts[1] = 0; $parts[2] = 0 }
        'minor' { $parts[1]++; $parts[2] = 0 }
        'patch' { $parts[2]++ }
    }
    $newVersion = $parts -join '.'
}

if ($newVersion -eq $currentVersion) {
    Write-Host "Versione gia' a $newVersion, nulla da fare." -ForegroundColor Yellow
    exit 0
}

(Get-Content $configPath -Raw) -replace 'version:\s*"\d+\.\d+\.\d+"', "version: `"$newVersion`"" |
    Set-Content $configPath -NoNewline

$pkgContent = Get-Content $pkgPath -Raw
if ($pkgContent -notmatch '"version":\s*"\d+\.\d+\.\d+"') {
    throw "Impossibile trovare '`"version`": `"X.Y.Z`"' in $pkgPath"
}
($pkgContent -replace '"version":\s*"\d+\.\d+\.\d+"', "`"version`": `"$newVersion`"") |
    Set-Content $pkgPath -NoNewline

Write-Host "Versione aggiornata: $currentVersion -> $newVersion" -ForegroundColor Green
Write-Host "  - config.yaml" -ForegroundColor Green
Write-Host "  - frontend/package.json" -ForegroundColor Green
Write-Host ''
Write-Host 'Prossimi passi: ./deploy-addon.ps1  poi  Rebuild (non solo Restart) dell add-on da Home Assistant.' -ForegroundColor Cyan
