#!/bin/bash
# Instalação do Sistema de Envio (Mac). Dê dois cliques (na 1ª vez: botão
# direito > Abrir). Prepara o Python, as dependências e o atalho na Mesa.
cd "$(dirname "$0")" || exit 1
PASTA="$(pwd)"
DADOS="$HOME/Library/Application Support/Sistema de Envio"
VENV="$DADOS/python"

clear
echo "============================================"
echo "  Instalando o Sistema de Envio (Mac)"
echo "============================================"
echo

# Libera os arquivos baixados da internet (evita o bloqueio do macOS).
xattr -dr com.apple.quarantine "$PASTA" 2>/dev/null

# 1/4 - Python 3.10+ com tkinter 8.6 (o do python.org é o recomendado).
echo "[1/4] Procurando o Python..."
PY=""
for candidato in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
  if [ -x "$candidato" ] && "$candidato" -c 'import sys, tkinter; assert sys.version_info >= (3, 10) and tkinter.TkVersion >= 8.6' 2>/dev/null; then
    PY="$candidato"
  fi
done
if [ -z "$PY" ]; then
  for candidato in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c 'import sys, tkinter; assert sys.version_info >= (3, 10) and tkinter.TkVersion >= 8.6' 2>/dev/null; then
      PY="$candidato"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo
  echo "Nao achei um Python 3.10 ou mais novo com a parte grafica (tkinter)."
  echo "Instale o Python do site python.org (botao 'Download Python 3...'),"
  echo "depois de dois cliques de novo neste instalar.command."
  open "https://www.python.org/downloads/macos/"
  echo
  read -r -p "Aperte ENTER para fechar."
  exit 1
fi
echo "      Usando: $PY ($("$PY" --version))"
VERSAO="$("$PY" -c 'import sistema_envio; print(sistema_envio.__version__)' 2>/dev/null)"
echo "      Versao do programa: ${VERSAO:-?}"

# 2/4 - Ambiente proprio do programa (fica na pasta de dados: sobrevive a troca de versao).
echo "[2/4] Preparando o ambiente do programa..."
mkdir -p "$DADOS"
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c 'import tkinter' 2>/dev/null; then
  rm -rf "$VENV"
  "$PY" -m venv "$VENV" || { echo "Falha ao criar o ambiente."; read -r -p "ENTER para fechar."; exit 1; }
fi

# 3/4 - Dependencias (so baixa o que falta).
echo "[3/4] Verificando as dependencias..."
if "$VENV/bin/python" -c 'import openpyxl, keyring, certifi, PIL' 2>/dev/null; then
  echo "      Tudo ja instalado - nada a baixar."
else
  echo "      Baixando (pode levar alguns minutos)..."
  if ! "$VENV/bin/python" -m pip install --disable-pip-version-check --timeout 60 -r requirements.txt; then
    echo
    echo "Falha ao instalar as dependencias. Verifique a internet e rode de novo."
    read -r -p "Aperte ENTER para fechar."
    exit 1
  fi
fi

# 4/4 - Atalho na Mesa (Desktop).
echo "[4/4] Criando o atalho na Mesa..."
ATALHO="$HOME/Desktop/Sistema de Envio.command"
printf '#!/bin/bash\nexec "%s/iniciar.command"\n' "$PASTA" > "$ATALHO"
chmod +x "$ATALHO" "$PASTA/iniciar.command" "$PASTA/instalar.command"

echo
echo "============================================"
echo "  Pronto! Versao ${VERSAO:-?} instalada em:"
echo "  $PASTA"
echo
echo "  Atalho na Mesa: \"Sistema de Envio\""
echo
echo "  Para atualizar: apague esta pasta e extraia o"
echo "  zip novo no mesmo lugar. Nao precisa rodar"
echo "  este instalador de novo."
echo
echo "  Seus dados (historico e configuracoes) ficam em:"
echo "  $DADOS"
echo "============================================"
open "$PASTA"
echo
read -r -p "Aperte ENTER para fechar."
