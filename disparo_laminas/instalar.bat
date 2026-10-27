@echo off
chcp 65001 >nul
title Instalacao - Disparo de Laminas
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto sem_python

set "VERSAO=?"
for /f "delims=" %%v in ('%PY% -c "import laminas; print(laminas.__version__)" 2^>nul') do set "VERSAO=%%v"

echo ============================================
echo   Instalando o Disparo de Laminas
echo   Versao %VERSAO%
echo ============================================
echo.
echo Dica: se a janela parecer parada, aperte ENTER.
echo O Windows pausa esta janela quando voce clica dentro dela.
echo.

echo [1/3] Verificando o que ja esta instalado...
%PY% -c "import openpyxl, win32com.client, PIL" >nul 2>nul
if not errorlevel 1 goto dependencias_ok

echo [2/3] Baixando e instalando as dependencias. Pode levar alguns minutos...
%PY% -m pip install --disable-pip-version-check --timeout 60 -r requirements.txt
if errorlevel 1 goto falha_pip
goto atalho

:dependencias_ok
echo [2/3] Dependencias ja instaladas - nada a baixar.

:atalho
echo [3/3] Criando o atalho na Area de Trabalho...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Disparo de Laminas.lnk'); $s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.IconLocation=$env:SystemRoot+'\System32\shell32.dll,156'; $s.Save()"

echo.
echo ============================================
echo   Pronto! Versao %VERSAO% instalada em:
echo   %~dp0
echo.
echo   Atalho na Area de Trabalho:
echo   "Disparo de Laminas"
echo.
echo   Para atualizar de versao basta extrair o zip
echo   novo por cima desta pasta - nao precisa
echo   rodar este instalador de novo.
echo ============================================
echo.
echo Abrindo a pasta do programa...
explorer "%~dp0"
pause
exit /b 0

:sem_python
echo Python nao encontrado neste computador.
echo Instale o Python e MARQUE a opcao "Add Python to PATH".
echo Depois rode este instalar.bat de novo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:falha_pip
echo.
echo Falha ao instalar as dependencias.
echo Verifique a internet e rode o instalar.bat de novo.
echo Em rede corporativa, o proxy/firewall pode estar bloqueando o pip.
pause
exit /b 1
