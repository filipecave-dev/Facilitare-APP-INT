# Disparo de Lâminas

Programa em Python que substitui a macro **Macro_Laminas** (Excel/VBA) no
envio das lâminas de prospecção — pelo **Outlook** ou direto pelo servidor de
e-mail do **subdomínio de prospecção** (SMTP). Roda no seu PC (Windows), com
uma tela simples.

## O que ele faz

1. **Campanhas salvas**: você monta a campanha (pasta de lâminas, lâmina(s),
   apresentação anexada e texto) e clica em **Salvar campanha...**, dando um
   nome (ex.: "Corporativo - Prazo 70 dias"). Depois é só escolher na lista
   **Campanha** e tudo é carregado. Dá para escolher uma lâmina ou **mesclar
   várias** (cada envio usa a próxima, em rodízio). A **apresentação vai como
   anexo**: a institucional para Corporativo, a de eventos para Eventos.
2. **Lê a lista de envio** de uma planilha (`.xlsx`, `.xlsm` ou `.csv`) — pode
   ser a própria aba "A ENVIAR" da macro. As colunas de **Nome**, **Empresa** e
   **E-mail** são encontradas pelo título, **em qualquer ordem** (aceita também
   "Nome Completo", "Contato", "Razão Social", "E-mail Principal",
   "Primeiro Nome" + "Sobrenome" etc.). A linha **Colunas**, logo abaixo da
   planilha, mostra o que foi encontrado e permite trocar manualmente; a
   escolha fica lembrada para aquela planilha/aba. O nome e a empresa de cada
   linha substituem `{nome}` e `{empresa}` no assunto e no texto.
3. **Aponta os problemas antes do disparo**:
   - 🔴 **e-mail duplicado na base** — avisa quais e-mails se repetem e em
     quais linhas; só a primeira ocorrência pode ser enviada;
   - 🟡 **já enviado** — o e-mail já recebeu lâmina (fica desmarcado; só
     reenvia se você confirmar);
   - ⚪ **inválido** — e-mail mal formado ou faltando nome/empresa.
4. **Você escolhe quem recebe e quem leva cópia (CC)**: clique na coluna
   *Enviar* ou *CC* de cada linha (ou selecione várias linhas e use os botões).
   O e-mail da cópia (ex.: Ricardo) fica no quadro 3 e nas Configurações.
5. **Dispara respeitando as regras**: no máximo **80 por dia** (conta também o
   que já saiu mais cedo no mesmo dia) e **3 minutos** entre um e-mail e outro.
   Os dois números são editáveis no próprio quadro 3 ("E-mails por dia" e
   "Intervalo entre e-mails") ou em Configurações.
   A tela mostra a contagem para o próximo envio; o botão **Parar** interrompe
   a qualquer momento (quem não foi enviado continua pendente).
6. **Registra tudo na aba Enviados** (data/hora, contato, cópia, campanha,
   lâmina, apresentação, remetente, status, versão). Dá para buscar, **exportar para Excel** e **importar os
   envios antigos** (abas RELATORIO / BASE-ENVIADO da macro) para que entrem no
   controle de duplicados.

Tudo é editável: limite diário, intervalo, e-mail de cópia, cópia oculta,
remetente/subdomínio, pasta das lâminas, largura da imagem, assunto e textos
(por campanha salva ou padrão).

## Campanhas salvas

No quadro **1. Campanha** da aba Disparo:

1. Escolha a **Pasta de lâminas**, selecione a(s) lâmina(s) e a
   **Apresentação**; na aba **Mensagem**, ajuste assunto e textos.
2. Clique em **Salvar campanha...** e digite o nome. Se o nome já existir, o
   programa pergunta se deve substituir.
3. Para usar depois, escolha a campanha na lista **Campanha**. A última usada
   já abre carregada.

Se você mudar algo de uma campanha carregada, aparece **● alterações não
salvas**; antes do disparo o programa oferece salvar. **Excluir** apaga só a
campanha salva — o histórico de envios não é alterado. O nome da campanha
fica registrado em cada envio da aba Enviados.

## Remetente das prospecções (subdomínio)

Em **Configurações → Remetente das prospecções**, escolha a forma de envio:

| Forma de envio | Quando usar | O que precisa |
|---|---|---|
| Outlook — conta padrão | como era antes | nada |
| Outlook — conta do subdomínio | a caixa do subdomínio está no Outlook | adicionar a conta no Outlook (Arquivo › Adicionar conta) e informar o endereço em *E-mail remetente* |
| Outlook — enviar como | Exchange / Microsoft 365 com permissão "Enviar como" | a permissão no servidor e o endereço em *E-mail remetente* |
| SMTP direto | o subdomínio tem servidor de e-mail próprio | servidor, porta, segurança, usuário e senha do SMTP (use **Testar conexão SMTP**) |

- **Subdomínio de envio** (ex.: `prospeccao.tivolitur.com.br`): o programa
  avisa se o remetente não for desse subdomínio ou se a forma de envio for a
  conta padrão.
- **Responder para** (opcional): para onde vão as respostas dos clientes —
  por exemplo, o seu e-mail do domínio principal.
- No **SMTP**, a senha fica protegida pelo Windows (só o seu usuário, neste
  computador, consegue ler), a assinatura do Outlook não entra (preencha
  **Assinatura (SMTP)**) e os e-mails não aparecem nos Itens Enviados do
  Outlook — use a **Cópia oculta (CCO)** se quiser guardar uma cópia.
- Para o subdomínio ter boa entrega, ele precisa de SPF, DKIM e DMARC
  configurados no DNS (com quem administra o domínio/servidor de e-mail).

## Versão

A versão em uso aparece no título da janela (ex.: *Disparo de Lâminas — versão
1.7.0*) e em cada envio da aba Enviados. O que mudou em cada versão está em
[HISTORICO_VERSOES.md](HISTORICO_VERSOES.md).

## Instalação (uma vez)

1. Instale o **Python 3.10+** em <https://www.python.org/downloads/> e, na
   instalação, marque **"Add Python to PATH"**.
2. Copie a pasta `disparo_laminas` para o seu computador.
3. Dê dois cliques em **`instalar.bat`**. Ao terminar ele mostra na tela onde
   o programa ficou instalado, abre essa pasta no Explorer e cria o atalho
   **"Disparo de Laminas"** na Área de Trabalho.

**Atualizar de versão:** cada zip é o programa **completo**. Pode apagar a
pasta antiga e extrair a nova no mesmo lugar (ou extrair por cima): seus dados
ficam em outra pasta (veja "Onde ficam os dados") e não se perdem. Não precisa
rodar o `instalar.bat` de novo (só se uma versão pedir isso no
[HISTORICO_VERSOES.md](HISTORICO_VERSOES.md)).

Para abrir o programa: dois cliques no atalho **Disparo de Laminas** da Área
de Trabalho (ou em **`iniciar.bat`** dentro da pasta). O Outlook precisa estar
instalado e configurado com a sua conta.

## Organização das lâminas

A pasta das lâminas (Configurações → *Pasta das lâminas*) deve ter **uma
subpasta por campanha**, cada uma com as imagens (`.jpg`, `.jpeg`, `.png`,
`.gif`):

```
LAMINAS PROSPECT/
├── CORPORATIVO/   Tivolitur-0426.jpeg
├── EVENTOS/       ...
└── INCENTIVO/     ...
```

A lâmina mais recente da campanha já vem selecionada.

### Apresentações (anexo)

As apresentações ficam na subpasta **APRESENTAÇÃO** (ela não aparece como
campanha):

```
LAMINAS PROSPECT/
└── APRESENTAÇÃO/
    ├── Apresentação Institucional ....pdf   → anexada em CORPORATIVO
    └── Apresentação Eventos ....pdf         → anexada em EVENTOS
```

O programa escolhe a apresentação pelo **nome do arquivo**: "institucional"
(ou "corporativo") para Corporativo, "evento" para Eventos e o nome da
campanha para as demais. No quadro 1, em **Apresentação (anexo)**, dá para
trocar o arquivo ou escolher *(sem anexo)*; a escolha fica lembrada para
aquela campanha. O tamanho do arquivo aparece ao lado (acima de 15 MB o
programa avisa, pois o servidor pode recusar). A aba Enviados registra qual
apresentação foi anexada em cada envio. Por padrão a pasta é
`OneDrive - Veronezzi Serviços Comerciais LTDA\DOCUMENTOS\TIVOLITUR\LAMINAS PROSPECT`
dentro da sua pasta de usuário.

## Primeiro uso — passo a passo

1. **Configurações**: confira a pasta das lâminas, o e-mail de cópia (Ricardo),
   o limite (80) e o intervalo (3 min). Clique em **Salvar configurações**.
2. **Enviados → Importar envios anteriores…**: escolha a planilha da macro e
   marque as abas **RELATORIO** e **BASE-ENVIADO**. Assim quem já recebeu não
   recebe de novo.
3. **Mensagem**: ajuste o assunto e os textos. Campos disponíveis:
   `{nome}`, `{primeiro_nome}`, `{empresa}` e `{saudacao}` ("bom dia" antes das
   12h, "boa tarde" depois). Salve **para esta campanha** ou **como padrão**.
4. **Disparo**:
   1. escolha a **campanha** e a(s) **lâmina(s)**;
   2. escolha a **planilha** e a **aba** e clique em **Carregar**;
   3. confira os avisos de duplicados, marque quem vai receber e quem leva
      **CC**;
   4. clique em **Pré-visualizar** (abre o e-mail no Outlook sem enviar) e,
      se quiser, em **Enviar teste...** (envia de verdade para o endereço que
      você digitar, com "[TESTE]" no assunto, sem cópia e sem entrar na lista
      de enviados);
   5. clique em **Iniciar disparo** e confirme o resumo.

> Para testar sem enviar nada, ligue o **Modo simulação** nas Configurações:
> os e-mails viram arquivos HTML na pasta `dados/simulacao`.

Deixe o programa aberto durante o disparo (80 e-mails × 3 min ≈ 4 horas). O
programa impede que o Windows entre em suspensão enquanto envia.

## Onde ficam os dados

Fora da pasta do programa, em **`%APPDATA%\Disparo de Laminas`** (cole esse
endereço na barra do Explorer, ou use Configurações → *Abrir pasta de dados*):

- `config.json` — configurações e mensagens;
- `historico_envios.db` — lista de enviados (controle de duplicados);
- `simulacao\` — e-mails gerados no modo simulação.

**Não apague essa pasta**: é ela que impede reenviar para quem já recebeu.
O programa faz **backup automático** do histórico e das configurações ao
abrir (um por dia e a cada versão nova) em `backups\`, guardando os 30 mais
recentes. Para restaurar, copie o arquivo do backup de volta para a pasta de
dados com o programa fechado.

## Para desenvolvedores

O núcleo (`base`, `historico`, `mensagem`, `campanhas`, `disparo`) não depende
do Outlook nem da tela e é coberto por `tests/test_disparo_laminas.py`
(`pytest` na raiz do repositório). `envio.py` fala com o Outlook via
`pywin32` (COM) e `app.py` é a tela em `tkinter`.
