# Pubblica l'add-on: aggiorna il branch 'publish' con l'ultimo 'main' e lo pusha,
# facendo partire la CI (.github/workflows/publish-addon.yml) che sincronizza
# i sorgenti su ha-addons/gestionecontabile.
#
# Ricorda di bumpare la versione (./bump-version.ps1) e committare su main PRIMA
# di lanciare questo script, altrimenti pubblichi la versione gia' esistente.

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

Push-Location $root
try {
    $status = git status --porcelain
    if ($status) {
        throw "Ci sono modifiche non committate. Committa o stasha prima di pubblicare:`n$status"
    }

    $originalBranch = git rev-parse --abbrev-ref HEAD

    Write-Host 'Aggiorno i riferimenti remoti...' -ForegroundColor Cyan
    git fetch origin

    git checkout publish
    git merge origin/main --ff-only

    Write-Host 'Pusho su publish...' -ForegroundColor Cyan
    git push origin publish

    git checkout $originalBranch

    Write-Host 'Pubblicato: la CI su GitHub sincronizzera i sorgenti su ha-addons/gestionecontabile.' -ForegroundColor Green
} finally {
    Pop-Location
}
