# SEPA FraudGuard - Setup Windows PowerShell
# Lancez ce script avec : .\setup.ps1

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SEPA FraudGuard - Installation & Setup Windows" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Verifier Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] $pyVersion detecte" -ForegroundColor Green
} catch {
    Write-Host "[ERREUR] Python non trouve !" -ForegroundColor Red
    Write-Host "  Installez Python 3.10+ depuis : https://python.org/downloads" -ForegroundColor Yellow
    Write-Host "  Cochez 'Add Python to PATH' lors de l'installation !" -ForegroundColor Yellow
    Read-Host "Appuyez sur Entree pour quitter"
    exit 1
}

# Installer les dependances
Write-Host ""
Write-Host "[1/3] Installation des dependances Python..." -ForegroundColor Yellow
pip install scikit-learn joblib numpy pandas

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERREUR] Echec de l'installation pip" -ForegroundColor Red
    Read-Host "Appuyez sur Entree pour quitter"
    exit 1
}

Write-Host ""
Write-Host "[OK] Dependances installes !" -ForegroundColor Green

# Aller dans le bon repertoire
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
Write-Host "[OK] Repertoire : $ScriptDir" -ForegroundColor Green

# Lancer le pipeline
Write-Host ""
Write-Host "[2/3] Generation du dataset + Entrainement des modeles..." -ForegroundColor Yellow
Write-Host "(Cela peut prendre 1-2 minutes)" -ForegroundColor Gray
Write-Host ""
python train.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERREUR] Echec du pipeline d'entrainement" -ForegroundColor Red
    Read-Host "Appuyez sur Entree pour quitter"
    exit 1
}

Write-Host ""
Write-Host "[3/3] Lancement de la demonstration..." -ForegroundColor Yellow
Write-Host ""
python demo_client.py

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Installation terminee !" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Commandes disponibles :" -ForegroundColor Cyan
Write-Host "    python train.py        -> Reentrainer les modeles" -ForegroundColor White
Write-Host "    python api.py          -> Demarrer l'API sur http://localhost:8000" -ForegroundColor White
Write-Host "    python demo_client.py  -> Demo scoring" -ForegroundColor White
Write-Host "    python tests\test_fraud_api.py  -> Tests" -ForegroundColor White
Write-Host ""
Read-Host "Appuyez sur Entree pour quitter"
