@echo off
chcp 65001 >nul
title Installation - Fabrication Beton Kourayzen
cd /d "%~dp0"

echo ================================================
echo    INSTALLATION - Fabrication Beton
echo    Chantier Kourayzen
echo ================================================
echo.
echo Ce script installe les dependances Python
echo necessaires a l'application.
echo A faire UNE SEULE FOIS.
echo.
pause

echo.
echo [1/3] Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo.
    echo --------- QUE FAIRE ? ---------
    echo 1. Va sur https://www.python.org/downloads/
    echo 2. Telecharge la derniere version pour Windows
    echo 3. Lance l'installeur
    echo 4. IMPORTANT : coche la case "Add Python to PATH" en bas
    echo    de l'ecran d'installation, AVANT de cliquer sur Install
    echo 5. Relance ce script INSTALLER.bat
    echo -------------------------------
    echo.
    pause
    exit /b 1
)
echo Python detecte :
python --version
echo.

echo [2/3] Mise a jour de pip (gestionnaire de paquets)...
python -m pip install --upgrade pip
echo.

echo [3/3] Installation des dependances (peut prendre 1 a 2 minutes)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation des dependances a echoue.
    echo Verifie ta connexion internet et relance ce script.
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================
echo    INSTALLATION TERMINEE avec succes !
echo ================================================
echo.
echo Pour lancer l'application maintenant :
echo    double-clique sur LANCER_APP.bat
echo.
pause
