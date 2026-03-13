@echo off
echo ============================================================
echo   SEPA FraudGuard - Installation Windows
echo ============================================================
echo.

:: Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Installez Python 3.10+ depuis python.org
    pause
    exit /b 1
)

echo [1/3] Installation des dependances Python...
pip install scikit-learn joblib numpy pandas 2>&1
if errorlevel 1 (
    echo [ERREUR] Echec installation. Verifiez votre connexion internet.
    pause
    exit /b 1
)

echo.
echo [2/3] Dependances installees avec succes !
echo.
echo [3/3] Lancement du pipeline (dataset + entrainement)...
echo.
python train.py

echo.
echo ============================================================
echo   Installation terminee !
echo   Commandes disponibles :
echo     python train.py        -^> Entrainer les modeles
echo     python api.py          -^> Demarrer l'API (port 8000)
echo     python demo_client.py  -^> Demo scoring
echo ============================================================
pause
