# Histórico de versões — Disparo de Lâminas

A versão aparece no título da janela, na aba Configurações, no nome do pacote
(`disparo_laminas_vX.Y.Z.zip`) e na coluna **Versão** de cada envio registrado
na aba Enviados.

## 1.7.1 — 30/10/2026
- **Correção:** só o 1º e-mail de cada disparo saía; os seguintes davam
  "Falha ao criar o e-mail no Outlook" e o disparo parava após 3 erros. O
  Outlook (COM) agora roda na thread da tela, que atende as mensagens do
  Windows, como a pré-visualização — a thread do disparo só espera os
  intervalos e pede cada envio.
- Se a ligação com o Outlook cair entre um envio e outro, o programa
  reconecta sozinho e monta o e-mail de novo (anotado em Obs.).
- Quando o envio direto é recusado uma vez, os seguintes já saem abrindo a
  janela do e-mail (como a macro), sem tentar o envio direto de novo.
- Aba Enviados: duplo clique numa linha mostra o registro completo (o erro
  não fica cortado) com botão Copiar.

## 1.7.0 — 30/10/2026
- **Campanhas salvas:** lista "Campanha" no quadro 1 para escolher e botão
  **Salvar campanha...**, que pede o nome. Cada campanha guarda a pasta, a(s)
  lâmina(s), o "Mesclar", a apresentação e o texto (assunto, texto de cima e
  de baixo). Botão **Excluir**. Aviso "● alterações não salvas" e, antes do
  disparo, oferta de salvar as alterações. A última campanha usada abre
  carregada. O histórico registra o nome da campanha salva.
- **Ritmo na tela de disparo:** "E-mails por dia" e "Intervalo entre e-mails"
  editáveis no quadro 3 (também em Configurações).
- **Subdomínio de envio:** quadro "Remetente das prospecções" em
  Configurações, com 4 formas de envio: conta padrão do Outlook, conta do
  subdomínio cadastrada no Outlook, Outlook "enviar como" o endereço do
  subdomínio, ou **SMTP direto** no servidor do subdomínio (servidor, porta,
  segurança, usuário, senha protegida pelo Windows, assinatura e botão
  "Testar conexão SMTP"). "Responder para" opcional. Avisos quando o
  remetente não é do subdomínio. O histórico registra o remetente de cada
  envio.
- A configuração antiga "Conta do Outlook que envia" vira automaticamente a
  forma "conta do subdomínio cadastrada no Outlook".
- **Backup automático** do histórico e das configurações ao abrir (um por dia
  e a cada versão nova), em `backups`, guardando os 30 mais recentes.
- Aba Configurações com barra de rolagem.

## 1.6.0 — 27/10/2026
- **Dados fora da pasta do programa:** configurações (`config.json`),
  histórico de enviados e simulações passam a ficar em
  `%APPDATA%\Disparo de Laminas`. Agora dá para apagar a pasta do programa e
  extrair a versão nova (pacote completo) sem perder o controle de enviados.
- Na primeira abertura, o `config.json` e o histórico que estiverem na pasta
  do programa (versões até 1.5.1) são copiados para a pasta de dados.
- O log de abertura e a aba Configurações mostram onde os dados estão.

## 1.5.1 — 27/10/2026
- Instalador: não reinstala/atualiza o que já está instalado (antes usava
  `--upgrade` e consultava a internet a cada execução, parecendo travado);
  mostra a versão, as etapas [1/3]...[3/3] e a dica de apertar ENTER se a
  janela pausar; mensagem clara em caso de falha do pip.

## 1.5.0 — 27/10/2026
- Número de versão visível: título da janela, aba Configurações, registro de
  abertura no log e nome do pacote zip.
- Cada envio registrado na aba Enviados (e na exportação para Excel) guarda a
  versão do programa que o enviou.
- Este histórico de versões.

## 1.4.0 — 27/10/2026
- Quando o Outlook recusa o envio direto (*Send*) com "Parâmetro incorreto",
  o programa abre a janela do e-mail e envia em seguida, como a macro fazia.
- O contorno usado fica anotado em Obs. na aba Enviados.
- A lâmina deixa de ser marcada como anexo oculto.
- Botão **Enviar teste...**: envia o e-mail montado para um endereço de
  teste, sem CC e sem registrar na lista de enviados.

## 1.3.0 — 27/10/2026
- Erros do Outlook dizem a etapa que falhou (criar, destinatários, lâmina,
  apresentação, assinatura, envio) e o código traduzido.
- Anexo recusado (OneDrive, acentos no caminho) é reenviado a partir de uma
  cópia local.
- O disparo para sozinho após 3 erros seguidos.

## 1.2.0 — 27/10/2026
- Apresentação da campanha enviada como anexo, a partir da pasta
  `APRESENTAÇÃO` (institucional para Corporativo, eventos para Eventos), com
  troca manual lembrada por campanha.
- Coluna Anexo na aba Enviados.

## 1.1.0 — 27/10/2026
- Nome e empresa lidos da planilha em qualquer ordem de colunas e com títulos
  variados; linha **Colunas** para conferir e trocar o mapeamento.
- Pré-visualização bloqueada para contato sem nome ou empresa.
- Instalador cria atalho na Área de Trabalho e mostra a pasta instalada.

## 1.0.0 — 27/10/2026
- Primeira versão: campanha e lâmina, lista de envio com aviso de duplicados,
  CC por contato, limite diário de 80, intervalo de 3 minutos, lista de
  enviados com exportação/importação e modo simulação.
