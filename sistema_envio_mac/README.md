# Sistema de Envio — Mac

Versão para **macOS** do Disparo de Lâminas: envia as lâminas de prospecção
direto pelo servidor de e-mail (**SMTP**) do **subdomínio de prospecção**.
Projeto separado, com versão própria (veja [HISTORICO_VERSOES.md](HISTORICO_VERSOES.md)).

> Por que SMTP e não Outlook? O Outlook do Mac não aceita o controle
> automático que o programa usa no Windows. O SMTP não depende de nenhum app
> de e-mail e é o caminho recomendado para prospecção por subdomínio.

## O que ele faz

1. **Campanhas salvas** — pasta de lâminas, lâmina(s), apresentação anexada e
   texto, com nome (ex.: "Corporativo - Prazo 70 dias"). Escolha na lista
   **Campanha**; **Salvar campanha...** pede o nome.
2. **Lê a planilha** (`.xlsx`, `.xlsm`, `.csv`) — Nome, Empresa e E-mail em
   qualquer ordem de colunas; linha **Colunas** para conferir/trocar.
3. **Aponta duplicados** na base (🔴), quem **já recebeu** (🟡) e e-mails
   inválidos (⚪).
4. **Cópia (CC)** escolhida contato a contato.
5. **Ritmo**: até **80 e-mails por dia** e **3 minutos** entre eles —
   editáveis no quadro 3 ou em Configurações. O Mac não dorme durante o
   disparo.
6. **Enviados**: histórico com campanha, lâmina, apresentação, remetente e
   versão; busca, exportação para Excel, duplo clique para o detalhe.

## Instalação (uma vez)

1. Instale o **Python** do site oficial: <https://www.python.org/downloads/macos/>
   (botão *Download Python 3…*). Use o do python.org: o do Homebrew vem sem a
   parte gráfica.
2. Extraia o zip numa pasta fixa (ex.: **Documentos**).
3. Na pasta `sistema_envio_mac`, clique com o **botão direito** em
   **`instalar.command`** › **Abrir** › **Abrir** (na 1ª vez o macOS pede essa
   confirmação por ser um arquivo baixado).
4. Ao final aparece o atalho **"Sistema de Envio"** na Mesa (Desktop).

Para abrir: dois cliques no atalho da Mesa (ou em `iniciar.command`). Abre
uma janela do Terminal junto — pode fechá-la, o programa continua.

**Atualizar de versão:** apague a pasta antiga e extraia o zip novo no mesmo
lugar. Não precisa instalar de novo (a não ser que o histórico de versões
peça).

## Configurar o envio (subdomínio)

Em **Configurações › Remetente das prospecções**:

1. **Provedor do e-mail** — escolha (Microsoft 365, Google Workspace,
   Locaweb, Hostinger, Zoho) e servidor, porta e segurança são preenchidos.
   Se não estiver na lista, escolha *Outro* e peça os dados a quem administra
   o e-mail.
2. **Subdomínio de envio** (ex.: `prospeccao.tivolitur.com.br`), **E-mail
   remetente** (ex.: `comercial@prospeccao.tivolitur.com.br`) e **Nome do
   remetente**.
3. **Responder para** (opcional) — para onde vão as respostas (ex.: seu
   e-mail principal).
4. **Usuário** e **Senha** do SMTP — a senha fica nas **Chaves do macOS**.
   - Microsoft 365: o administrador precisa permitir "SMTP autenticado" na
     caixa.
   - Google: use uma *senha de app* (com verificação em 2 etapas).
5. **Assinatura** — texto que entra no fim de cada e-mail.
6. **Testar conexão SMTP**, depois **Salvar configurações**.

Os e-mails enviados por SMTP não aparecem em nenhum app de e-mail: use a
**Cópia oculta (CCO)** para guardar uma cópia. Para boa entrega, o subdomínio
precisa de **SPF, DKIM e DMARC** no DNS.

## Trazer os dados do Windows

Para o Mac saber quem já recebeu:

1. No Windows, cole `%APPDATA%\Disparo de Laminas` na barra do Explorer e
   copie essa pasta para o Mac (pendrive, OneDrive, e-mail…).
2. No Mac: **Configurações › Importar dados do Windows...** e escolha a pasta.

Vêm o histórico de enviados (mesclado, sem duplicar), limite, intervalo,
cópias, textos, campanhas salvas e dados do SMTP. **Não** vêm a senha do SMTP
(protegida pelo Windows) nem os caminhos de pastas — ajuste a *Pasta das
lâminas* (no Mac o OneDrive fica em `~/Library/CloudStorage/OneDrive-…`).

## Organização das lâminas

```
LAMINAS PROSPECT/
├── CORPORATIVO/   lâminas (.jpg, .jpeg, .png, .gif)
├── EVENTOS/       ...
└── APRESENTAÇÃO/  apresentações anexadas (institucional, eventos...)
```

## Onde ficam os dados

Em **`~/Library/Application Support/Sistema de Envio`** (Configurações ›
*Abrir pasta de dados*): `config.json`, `historico_envios.db` (controle de
duplicados), `simulacao/`, `backups/` (automáticos: um por dia e a cada
versão, os 30 mais recentes), `python/` (ambiente do programa) e
`erros.log`. **Não apague essa pasta.**

## Para desenvolvedores

Pacote `sistema_envio` (tkinter + `smtplib`). Testes:

```bash
cd sistema_envio_mac
python3 -m pytest tests
```
