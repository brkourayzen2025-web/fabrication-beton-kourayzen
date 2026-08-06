@echo off
chcp 65001 >nul
title Fabrication Beton - Mode Reseau (PC + Telephone)
cd /d "%~dp0"

echo ================================================
echo    FABRICATION BETON - Mode Reseau
echo    Accessible depuis PC et telephone
echo ================================================
echo.

REM --- Verifier Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe.
    echo Lance d'abord INSTALLER.bat
    pause
    exit /b 1
)

REM --- Verifier Streamlit ---
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Streamlit n'est pas installe.
    echo Lance d'abord INSTALLER.bat
    pause
    exit /b 1
)

REM --- Trouver l'adresse IP du PC ---
echo Recherche de l'adresse IP de ce PC...
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /R /C:"IPv4"') do (
    for /f "tokens=* delims= " %%b in ("%%a") do (
        echo   ==^> http://%%b:8501
    )
)
echo.
echo ------------------------------------------------
echo  SUR TON TELEPHONE :
echo  1. Connecte-toi au MEME WIFI que ce PC
echo     (ou partage la 4G du tel avec le PC)
echo  2. Ouvre le navigateur (Chrome, Safari...)
echo  3. Tape UNE des adresses http://... ci-dessus
echo     (souvent celle qui commence par 192.168...)
echo  4. Ajoute a l'ecran d'accueil pour l'avoir
echo     comme une application :
echo     - Chrome (Android) : menu 3 points ^> Ajouter a l'ecran
echo     - Safari (iPhone)  : bouton partage ^> Sur l'ecran d'accueil
echo ------------------------------------------------
echo.
echo Sur ce PC, tu peux ouvrir : http://localhost:8501
echo.
echo Pour arreter : ferme cette fenetre ou Ctrl+C
echo.

python -m streamlit run app.py --server.address 0.0.0.0 --server.headless true

echo.
echo Application arretee.
pause
