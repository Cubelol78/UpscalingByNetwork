@echo off
REM UpscalingByNetwork/Start_Server.bat
REM Script de lancement du serveur Windows

title UpscalingByNetwork - Serveur Distribue

echo.
echo =====================================
echo   UpscalingByNetwork - Serveur v1.0
echo =====================================
echo.

REM Verification de Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH
    echo.
    echo Veuillez installer Python 3.8+ depuis https://python.org
    echo.
    pause
    exit /b 1
)

echo [INFO] Python detecte
python --version

REM Changement vers le dossier serveur
cd /d "%~dp0server"

REM Verification de l'existence du fichier principal
if not exist "server_main.py" (
    echo [ERREUR] Fichier server_main.py non trouve
    echo Verifiez que vous etes dans le bon dossier
    pause
    exit /b 1
)

echo [INFO] Fichier serveur trouve

REM Installation des dependances si requirements.txt existe
if exist "requirements.txt" (
    echo [INFO] Installation des dependances...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ATTENTION] Erreur installation dependances
        echo Le serveur peut ne pas fonctionner correctement
        pause
    )
)

REM Verification des outils necessaires
echo [INFO] Verification des outils...

REM FFmpeg
if exist "ffmpeg\ffmpeg.exe" (
    echo [OK] FFmpeg trouve
) else (
    echo [ATTENTION] FFmpeg non trouve dans ffmpeg\
    echo Telechargez FFmpeg depuis https://ffmpeg.org/
)

REM Real-ESRGAN
if exist "realesrgan-ncnn-vulkan\realesrgan-ncnn-vulkan.exe" (
    echo [OK] Real-ESRGAN trouve
) else (
    echo [ATTENTION] Real-ESRGAN non trouve dans realesrgan-ncnn-vulkan\
    echo Telechargez Real-ESRGAN depuis https://github.com/xinntao/Real-ESRGAN/releases
)

echo.
echo [INFO] Demarrage du serveur...
echo Appuyez sur Ctrl+C pour arreter le serveur
echo.

REM Demarrage du serveur avec gestion des erreurs
python server_main.py %*

if errorlevel 1 (
    echo.
    echo [ERREUR] Le serveur s'est arrete avec une erreur
    echo Consultez les logs pour plus de details
) else (
    echo.
    echo [INFO] Serveur arrete normalement
)

echo.
pause