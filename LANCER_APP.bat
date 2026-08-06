@echo off
chcp 65001 >nul
title Fabrication Beton - Kourayzen
cd /d "%~dp0"

echo ================================================
echo    FABRICATION BETON - Chantier Kourayzen
echo ================================================
echo.

REM --- Verifier Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe.
    echo Lance d'abord INSTALLER.bat
    echo.
    pause
    exit /b 1
)

REM --- Verifier Streamlit ---
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Streamlit n'est pas installe.
    echo Lance d'abord INSTALLER.bat
    echo.
    pause
    exit /b 1
)

echo Lancement de l'application en cours...
echo.
echo ------------------------------------------------
echo   Le navigateur va s'ouvrir automatiquement
echo   sur http://localhost:8501
echo.
echo   Pour arreter l'application :
echo   appuie sur Ctrl+C dans cette fenetre
echo   ou ferme simplement cette fenetre.
echo ------------------------------------------------
echo.

python -m streamlit run app.py

echo.
echo Application arretee.
pause
