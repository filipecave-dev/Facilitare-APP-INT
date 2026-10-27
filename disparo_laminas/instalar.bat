@echo off
cd /d "%~dp0"
echo Instalando dependencias do Disparo de Laminas...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo.
  echo Falha na instalacao. Confira se o Python esta instalado e marcado no PATH.
) else (
  echo.
  echo Pronto! Agora use o iniciar.bat
)
pause
