# Histórico de versões — Sistema de Envio (Mac)

Projeto separado do **Disparo de Lâminas** (Windows), com numeração própria.
A versão aparece no título da janela, na aba Configurações, no nome do pacote
(`sistema_envio_mac_vX.Y.Z.zip`) e na coluna **Versão** de cada envio.

## 1.0.0 — 03/11/2026
Primeira versão para macOS, feita a partir do Disparo de Lâminas 1.7.1.

- **Envio por SMTP** direto no servidor de e-mail do subdomínio de
  prospecção (o Outlook do Mac não permite a automação usada no Windows).
  Provedores pré-configurados: Microsoft 365, Google Workspace, Locaweb,
  Hostinger, Zoho ou outro. Botão "Testar conexão SMTP".
- Senha do SMTP guardada nas **Chaves do macOS** (Acesso às Chaves).
- Certificados de segurança do pacote `certifi` (o Python do python.org no
  Mac não usa os do sistema).
- Dados em `~/Library/Application Support/Sistema de Envio`, fora da pasta do
  programa: dá para apagar a pasta e extrair a versão nova sem perder nada.
- **Importar dados do Windows**: histórico de enviados (mesclado, sem
  duplicar), configurações, textos e campanhas salvas.
- `instalar.command` (Python, ambiente próprio, dependências e atalho na Mesa)
  e `iniciar.command`.
- Mac não dorme durante o disparo (`caffeinate`); Cmd+Q pergunta antes de
  sair no meio de um disparo; pré-visualização abre no app Mail.
- Mantido do Disparo de Lâminas: campanhas salvas, lâminas e apresentação por
  campanha, leitura da planilha em qualquer ordem de colunas, aviso de
  duplicados, CC por contato, limite diário e intervalo editáveis, lista de
  Enviados com exportação/importação, modo simulação, backups automáticos.
