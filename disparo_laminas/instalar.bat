@echo off
chcp 65001 >nul
title Instalacao - Disparo de Laminas
cd /d "%~dp0"
echo ============================================
echo   Instalando o Disparo de Laminas
echo ============================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python nao encontrado neste computador.
  echo Instale o Python e MARQUE a opcao "Add Python to PATH".
  echo Depois rode este instalar.bat de novo.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)

%PY% -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo.
  echo Falha ao instalar as dependencias. Verifique a internet e tente de novo.
  pause
  exit /b 1
)

rem Atalho na Area de Trabalho apontando para o iniciar.bat desta pasta
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Disparo de Laminas.lnk'); $s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.IconLocation=$env:SystemRoot+'\System32\shell32.dll,156'; $s.Save()"

echo.
echo ============================================
echo   Pronto! Programa instalado em:
echo   %~dp0
echo.
echo   Atalho criado na Area de Trabalho:
echo   "Disparo de Laminas"
echo ============================================
echo.
echo Abrindo a pasta do programa...
explorer "%~dp0"
pause
