# Agenda de Reuniões: rascunho automático no Outlook

Macro para o **Outlook clássico (Windows)**. Ela lê o seu calendário, onde
ficam as reuniões do Teams, aplica as regras abaixo e cria um **rascunho**
com a tabela "AGENDA DE REUNIÃO". Nada é enviado: o rascunho abre na tela
para você revisar.

Não precisa de administrador, Azure nem conector. Tudo roda no seu Outlook.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `AgendaReunioes.bas` | a macro (importar no Outlook) |
| `clientes.csv` | modelo da biblioteca de clientes da base ativa |

## Instalação (uma vez)

1. No Outlook: **Arquivo > Opções > Central de Confiabilidade > Configurações
   da Central de Confiabilidade > Configurações de Macro** e marque
   *"Notificações para todas as macros"*. Se essa tela estiver bloqueada pela
   empresa, a macro não roda. Nesse caso, me avise.
2. Pressione **Alt+F11** para abrir o editor de VBA.
3. **Arquivo > Importar arquivo...** e escolha `AgendaReunioes.bas`.
4. Salve com Ctrl+S e feche o editor.
5. Opcional: crie um botão. **Arquivo > Opções > Barra de Ferramentas de Acesso
   Rápido**, em "Escolher comandos em" selecione **Macros**, adicione
   `GerarRascunhoAgenda`.
6. Reinicie o Outlook. Na primeira execução ele pergunta se habilita as
   macros: escolha **Habilitar**.

## Uso

**Alt+F8** (ou o botão) e escolha a macro:

| Macro | O que faz |
|---|---|
| `GerarRascunhoAgenda` | pergunta data inicial/final e cria o rascunho |
| `GerarRascunhoAgendaPadrao` | sem perguntas: de hoje até +7 dias |
| `AbrirBibliotecaClientes` | abre o `clientes.csv` para editar |
| `AjustarUltimoNumero` | corrige o último número sequencial usado |

Na primeira execução:

- ela cria `Documentos\AgendaReunioes\clientes.csv` e o abre no Excel.
  Cadastre os clientes da base ativa, salve e rode de novo;
- ela pergunta o **último número de reunião já usado** (ex.: 126, para a
  próxima ser 127).

## Biblioteca de clientes (`clientes.csv`)

Abre no Excel. Uma linha por cliente da **base ativa**:

| EMPRESA | DOMINIOS | PALAVRAS NO ASSUNTO |
|---|---|---|
| TPL | tpl.com.br | TPL, Transportes TPL |
| Grupo ABC | abc.com.br, abcgroup.com | ABC |

- **EMPRESA**: nome como sai no e-mail.
- **DOMINIOS**: domínios de e-mail do cliente, separados por vírgula.
- **PALAVRAS NO ASSUNTO**: apelidos procurados no assunto da reunião,
  separados por vírgula. O nome da empresa já é procurado automaticamente.
  Maiúsculas e acentos são ignorados.

Ao salvar no Excel, mantenha o formato **CSV**: "CSV UTF-8" ou "CSV (separado
por vírgulas)", os dois funcionam.

## Regras de identificação

| Coluna | Regra |
|---|---|
| **REUNIÃO** | Reunião sua (você organizou, ou o cliente te convidou): **número sequencial**. Agendada por colega (organizador com e-mail da empresa) ou no local da sede: **000**. A mesma reunião mantém o mesmo número se você gerar o e-mail de novo. |
| **GERENTE / PARTICIPANTES** | Participantes internos (organizador primeiro). Salas são ignoradas. |
| **EMPRESA** | 1) domínio dos convidados externos na biblioteca; 2) cliente da biblioteca citado no assunto; 3) se for cliente novo: nome tirado do domínio (`@abc.com.br` vira ABC). Se o convidado só tem e-mail pessoal (gmail etc.), sai **(verificar)** e o assunto vai para a observação. |
| **DATA / HORÁRIO** | Início da reunião (dd/mm, hh:mm). |
| **FORMATO** | Link Teams/Zoom/Meet/Webex: **Virtual**; só local: **Presencial**; link + local: **Híbrido**. |
| **TIPO** | Cliente da biblioteca (base ativa): **Manutenção**. Cliente novo: **Prospecção**. |
| **OBSERVAÇÃO** | Local físico, quando houver. |

Ficam de fora: eventos de dia inteiro, reuniões canceladas ou recusadas e,
por padrão, reuniões só internas (sem convidado externo e sem cliente da
biblioteca no assunto).

## Ajustes (topo do arquivo `.bas`, bloco CONFIGURAÇÃO)

| Constante | Padrão | Para quê |
|---|---|---|
| `DESTINATARIOS` / `COPIA` | vazio | e-mails já preenchidos no rascunho |
| `ASSUNTO_EMAIL` | `Agenda de Reuniões - atualizada em {DATA}` | assunto |
| `DIAS_A_FRENTE` | 7 | período padrão |
| `LOCAIS_SEDE` | `sede` | textos do campo Local que indicam a sede da agência (separe por `;`) |
| `DOMINIOS_NAO_CLIENTES` | vazio | outras empresas do grupo, parceiros e fornecedores |
| `SOMENTE_REUNIOES_COM_CLIENTE` | True | False para listar todas as reuniões |
| `TIPO_CLIENTE_ATIVO` / `TIPO_CLIENTE_NOVO` | Manutenção / Prospecção | rótulos do tipo |

Para alterar: Alt+F11, abra o módulo `AgendaReunioes`, mude o valor e salve.

## Observações

- O "Novo Outlook" não roda macros. Use o Outlook clássico.
- O contador e os números de cada reunião ficam no registro do Windows
  (`HKEY_CURRENT_USER\Software\VB and VBA Program Settings\AgendaReunioes`).
  Gerar o rascunho já reserva o número da reunião, mesmo que o e-mail não
  seja enviado.
- Se uma reunião de uma série for remarcada para outro dia, ela recebe um
  número novo.
