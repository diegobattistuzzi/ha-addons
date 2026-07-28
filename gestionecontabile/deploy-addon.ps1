# Copia i sorgenti dell'add-on "Spese di casa" sulla share \addons di Home Assistant.
# Il Dockerfile builda il frontend e installa le dipendenze Python dentro il container,
# quindi servono solo i sorgenti: niente node_modules, __pycache__, dati locali, ecc.

param(
    [string]$Destination = '\\192.168.1.56\addons\gestionecontabile',
    [switch]$Mirror,   # con -Mirror, rimuove sul target i file non più presenti in origine (robocopy /MIR)
    [switch]$DryRun     # con -DryRun, mostra solo cosa verrebbe copiato (robocopy /L)
)

$ErrorActionPreference = 'Stop'
$Source = $PSScriptRoot

$excludeDirs = @(
    'node_modules',
    '__pycache__',
    '.git',
    '.claude',
    'dist',
    '.pytest_cache',
    'backend\src'   # vecchio backend Node.js dismesso, non serve più
)

$excludeFiles = @(
    '*.db', '*.db-shm', '*.db-wal',
    '.env',
    'options.json'
)

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
}

$robocopyArgs = @(
    $Source, $Destination,
    '/E',
    '/XD'
) + $excludeDirs + @('/XF') + $excludeFiles + @('/NFL', '/NDL', '/NP')

if ($Mirror) { $robocopyArgs += '/MIR' }
if ($DryRun) { $robocopyArgs += '/L' }

Write-Host "Copio da '$Source' a '$Destination'..." -ForegroundColor Cyan
if ($Mirror) { Write-Host 'Modalita MIRROR attiva: sul target verranno rimossi i file non presenti in origine.' -ForegroundColor Yellow }
if ($DryRun) { Write-Host 'Modalita DRY RUN: nessun file verra copiato davvero.' -ForegroundColor Yellow }

& robocopy @robocopyArgs

# Robocopy usa exit code < 8 per indicare successo (0-7), >= 8 per errori reali
if ($LASTEXITCODE -ge 8) {
    Write-Host "Robocopy ha restituito il codice $LASTEXITCODE — controlla l'output sopra." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host 'Copia completata.' -ForegroundColor Green
Write-Host 'Ricorda di riavviare/ricostruire l addon da Impostazioni -> Add-on -> Spese di casa in Home Assistant.' -ForegroundColor Cyan
