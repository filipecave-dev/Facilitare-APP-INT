#!/bin/bash
# Abre o Sistema de Envio (Mac). Pode fechar a janela do Terminal depois que
# o programa abrir: ele continua rodando.
cd "$(dirname "$0")" || exit 1
DADOS="$HOME/Library/Application Support/Sistema de Envio"
PY="$DADOS/python/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "Sistema de Envio" message "Antes de usar, de dois cliques em instalar.command (na pasta do programa)."'
  exit 1
fi
mkdir -p "$DADOS"
nohup "$PY" executar.py >> "$DADOS/erros.log" 2>&1 &
echo "Sistema de Envio aberto. Pode fechar esta janela do Terminal."
