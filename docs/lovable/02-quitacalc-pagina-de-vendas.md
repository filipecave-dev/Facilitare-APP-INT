# Script 2 — Página de vendas Facilitare QuitaCalc

**Onde usar:** num projeto Lovable **separado**. No projeto atual do site, use **Remix** (duplicar projeto) e aplique este prompt na cópia. Assim o layout, as cores, as fontes, o logo e a integração atual com o Asaas vêm iguais.
**Domínio:** próprio, por exemplo `www.quitacalc.com.br` `[CONFIRMAR]`. Sem ligação com o site da Facilitare.
**Como usar:** copie tudo a partir de "INÍCIO DO PROMPT" e cole no chat do Lovable. Se o Lovable cortar por tamanho, envie a Parte A numa mensagem e a Parte B na seguinte.

---

INÍCIO DO PROMPT

## PARTE A — Regras (não pular)

Este projeto passa a ser **somente a página de vendas do QuitaCalc**, uma landing page de uma página para campanhas. O visual atual está aprovado e **não pode mudar**.

### 1. O que NÃO alterar

- Não altere cores, tokens de tema, `index.css`, configuração do Tailwind nem o modo claro/escuro.
  - Referência (manter exatamente): fundo `oklch(100% 0 0)`, texto `oklch(18.61% .0294 259.81)`, primária `oklch(74.03% .1559 235.89)`, destaque `oklch(62.31% .188 259.81)`; no escuro, fundo `oklch(18.61% .0294 259.81)` e texto branco.
- Não altere as fontes: **Sora** nos títulos, **Inter** no texto.
- Não altere o logo nem o favicon.
- Não altere o layout, os espaçamentos, os botões, os cards nem os componentes da página `/quitacalc` atual. Ela vira a home deste projeto **com o mesmo visual**.
- **Não altere a lógica atual de cadastro antes do pagamento e o redirecionamento para o Asaas**. Só acrescente o que está no item 5.
- Não invente depoimentos, números de clientes, avaliações nem garantias.

### 2. Conteúdo editável (obrigatório)

- Todo o texto da página deve ficar em **um único arquivo**: `src/content/quitacalc.ts`, exportando um objeto tipado `quitacalc`.
- Os componentes leem desse arquivo. **Nenhum texto fixo dentro do JSX**: títulos, parágrafos, listas, botões, preço, preço antigo, prazo de acesso, perguntas e respostas, avisos, contatos, rodapé e SEO.
- Coloque `// EDITÁVEL` acima de cada bloco e use nomes de campo em português.
- Preço em campos separados: `preco.atual: 97`, `preco.anterior: 249`, `preco.rotulo: "Oferta de lançamento"`, `preco.condicao: "Pagamento único"`. A página formata como "R$ 97,00".
- Listas (benefícios, passos, público, perguntas, avisos) são arrays. Acrescentar ou remover item no array muda a tela.
- Seções opcionais têm `ativo: true/false`.
- Valores entre `[CONFIRMAR]` devem ir exatamente assim para o arquivo.

### 3. O que remover

- Remova todas as páginas e seções que não são do QuitaCalc: home institucional, Quem Somos, Soluções, Contato, FAQ separado e **Parceria jurídica**.
- Remova a parceria jurídica **por completo**: página, seção, textos, a opção "Quero uma avaliação jurídica do meu caso." do formulário de apoio, a pergunta sobre apoio jurídico do FAQ e o aviso de parceria do rodapé.
- **Nenhum link para o site da Facilitare** (nem no logo, nem no rodapé). O logo leva ao topo da própria página.
- Qualquer rota que não esteja na lista abaixo redireciona para `/`.

### 4. Rotas e estrutura

`/` (página de vendas) · `/obrigado` (após o pagamento, se o Asaas estiver configurado para voltar para cá `[CONFIRMAR]`) · `/politica-de-privacidade` · `/termos-de-uso`

**Cabeçalho:** logo + links de âncora (Como funciona · Preço · Dúvidas) + botão "Quero comprar" que rola até o cadastro.

**Ordem das seções em `/`:** Hero → Antes de negociar → O que você recebe → Como funciona → Para quem é → Oferta e cadastro → Apoio para a simulação → Dúvidas frequentes → Transparência → CTA final → Rodapé.

**Rodapé:** logo, WhatsApp e e-mail do QuitaCalc, links de Política e Termos, aviso curto da simulação, bloco do operador (`operador.ativo`) e "© {ano} QuitaCalc. Todos os direitos reservados."

### 5. Campanhas e medição (separadas da Facilitare)

- Capture na primeira visita `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `gclid` e `fbclid` (guardar em `sessionStorage`).
- Grave esses campos junto com o cadastro antes do pagamento e com o formulário de apoio (acrescente as colunas nas tabelas atuais, sem apagar dados).
- Em `quitacalc.ts`, crie `rastreamento: { ga4Id: "", metaPixelId: "", googleAdsId: "", googleAdsConversao: "" }`. Cada script só é carregado se o campo estiver preenchido.
- Eventos: `lead` ao enviar o cadastro, `begin_checkout` ao ir para o Asaas, `purchase` ao abrir `/obrigado`. Enviar para GA4, Meta Pixel (`Lead`, `InitiateCheckout`, `Purchase`) e Google Ads, quando configurados.
- `seo.indexar: true`. Se estiver `false`, adicionar `noindex` e bloquear no `robots.txt`.
- `sitemap.xml`, `robots.txt`, canonical e Open Graph usando `seo.urlBase` (editável).
- Segurança das tabelas: RLS ativado, visitante anônimo só pode **inserir**; leitura apenas para usuário autenticado.

## PARTE B — Conteúdo inicial de `src/content/quitacalc.ts`

Use exatamente estes textos.

### Geral
- marca: "QuitaCalc"
- seo.urlBase: "https://www.quitacalc.com.br [CONFIRMAR]"
- seo.title: "QuitaCalc — Negocie dívidas bancárias com mais informação"
- seo.description: "Organize os dados da sua dívida bancária, simule um cenário estimado e chegue mais preparado para negociar com o banco. R$ 97,00, acesso em até 24 horas."
- whatsapp: "5511916064145 [CONFIRMAR]"
- whatsappMensagem: "Olá! Quero saber mais sobre o QuitaCalc."
- email: "contato@quitacalc.com.br [CONFIRMAR]"
- operador: `{ ativo: false, razaoSocial: "[CONFIRMAR]", cnpj: "[CONFIRMAR]" }`

### Hero
- rótulo: "QuitaCalc"
- título: "Negocie sua dívida bancária com mais informação."
- subtítulo: "Organize os dados da sua dívida, simule um cenário estimado e chegue mais preparado para conversar com a instituição financeira."
- botão: "Quero comprar o QuitaCalc"
- selos: "Acesso digital + tutorial" · "Disponibilização em até 24 horas após a confirmação"
- cartão ilustrativo (manter o atual): "Simulação orientativa" · Dados da dívida: Organizados · Referência: Cenário estimado · Próximo passo: Negociar melhor · "Informação para apoiar sua preparação, sem substituir a proposta oficial da instituição credora."
- faixa de confiança: "Pagamento seguro no Asaas" · "Acesso em até 24 horas" · "Tutorial de uso incluído"

### Antes de negociar
- rótulo: "Antes de negociar"
- título: "Você não precisa entrar nessa conversa no escuro."
- texto: "Quando faltam referências, fica mais difícil avaliar uma proposta, formular perguntas e decidir o próximo passo. O QuitaCalc transforma os dados que você já possui em um cenário organizado para apoiar essa preparação."
- destaque: "Mais clareza para compreender o cenário. Mais segurança para conduzir a conversa."
- apoio: "Sem juridiquês e sem promessas irreais: uma ferramenta prática para quem deseja organizar informações antes de negociar."

### O que você recebe
- título: "Uma ferramenta simples para uma decisão importante"
- subtítulo: "O QuitaCalc ajuda você a transformar informações dispersas em uma referência compreensível para sua negociação."
- itens:
  - Visualize um cenário estimado — "Organize os dados da dívida e obtenha uma referência calculada para preparar sua conversa com a instituição financeira."
  - Negocie com mais clareza — "Saia do improviso com informações organizadas para avaliar propostas e conduzir uma negociação mais consciente."
  - Use uma lógica estruturada — "A ferramenta considera os dados informados e critérios de simulação apresentados de forma simples e direta."

### Como funciona
- título: "Do pagamento ao primeiro cálculo"
- passos:
  1. Adquira seu acesso — "Conclua o pagamento de R$ 97,00 com segurança no ambiente do Asaas." (o valor vem de `preco.atual`)
  2. Receba a ferramenta — "Em até 24 horas após a confirmação do pagamento, você receberá as orientações de acesso."
  3. Siga o tutorial — "Use o tutorial incluído para preencher as informações e compreender o cenário estimado."

### Para quem é
- título: "Para quem quer se preparar antes de negociar"
- texto: "O QuitaCalc foi pensado para pessoas que desejam compreender melhor os dados de uma dívida bancária e conversar com mais clareza."
- itens: "Pessoas físicas com dívidas bancárias em atraso" · "Pessoas que desejam se preparar antes de conversar com o banco" · "Quem quer organizar informações sem depender de cálculos improvisados" · "Quem entende que a decisão final de negociação pertence à instituição credora"

### Oferta e cadastro
- rótulo: "Oferta de lançamento"
- título: "Tenha acesso ao QuitaCalc"
- inclui: "Ferramenta digital QuitaCalc" · "Tutorial completo de uso" · "Orientações de acesso por e-mail" · "Uso da ferramenta após a liberação"
- prazo: "O acesso à ferramenta e ao tutorial será disponibilizado em até 24 horas após a confirmação do pagamento."
- preço: de R$ 249,00 por R$ 97,00 · "Pagamento único"
- cadastro: título "Para quem devemos enviar o acesso?" · texto "Salvamos seus dados para identificar a compra e enviar a ferramenta e o tutorial após a confirmação." · campos Nome completo*, E-mail*, WhatsApp* · consentimento "Autorizo o uso destes dados para identificar a compra, enviar o acesso e realizar comunicações sobre esta contratação, conforme a Política de Privacidade." · botão "Continuar para o pagamento" · nota "Você será direcionado ao ambiente seguro do Asaas."

### Apoio para a simulação
- rótulo: "Atendimento personalizado"
- título: "Precisa de ajuda para fazer sua simulação?"
- texto: "Conte o essencial do seu caso e nossa equipe entra em contato para ajudar você a preencher e entender a simulação."
- campos: Nome completo* · E-mail* · WhatsApp* · Banco ou instituição · Valor aproximado da dívida · Há quanto tempo está em atraso? · Quantidade de instituições · Breve descrição do caso* · "Já sou cliente do QuitaCalc." · consentimento
- botão: "Enviar solicitação"
- aviso: "Não envie senhas, dados bancários, informações de cartão ou documentos nesta etapa."
- sem o campo "Como podemos ajudar?" e sem opção jurídica.

### Dúvidas frequentes (acordeão)
1. **O QuitaCalc negocia a dívida por mim?** — Não. O QuitaCalc é uma ferramenta de cálculo e simulação. Ele ajuda a organizar informações e estimar cenários para que você se prepare melhor para uma conversa com a instituição financeira.
2. **O resultado apresentado é uma proposta oficial do banco?** — Não. O resultado é uma estimativa informativa. Somente a instituição financeira pode analisar o contrato e apresentar ou aceitar uma proposta oficial.
3. **A instituição financeira é obrigada a aceitar a simulação?** — Não. Somente a instituição credora pode analisar, validar, apresentar e aceitar uma proposta, conforme suas políticas e as circunstâncias do contrato.
4. **O QuitaCalc garante desconto ou quitação?** — Não. Nenhuma simulação pode garantir desconto, acordo, redução ou quitação. A análise e a decisão dependem exclusivamente da instituição financeira e das condições de cada caso.
5. **Quando receberei o acesso?** — O acesso à ferramenta e ao tutorial de uso será disponibilizado em até 24 horas após a confirmação do pagamento.
6. **Preciso entender de cálculos financeiros?** — Não. O QuitaCalc foi pensado para organizar o processo de forma simples, e você recebe um tutorial para acompanhar o uso da ferramenta.
7. **Posso desistir da compra?** — Sim. Você pode desistir em até 7 dias após a compra, conforme o Código de Defesa do Consumidor. [CONFIRMAR política de reembolso]
8. **Como falo com o suporte?** — Pelo WhatsApp ou pelo e-mail informados no rodapé desta página.

### Transparência
- título: "Informações importantes sobre a simulação"
- subtítulo: "Leia antes de usar os resultados do QuitaCalc em qualquer decisão."
- avisos (manter os 4 atuais, na íntegra):
  1. "A Resolução BCB nº 352 dispõe sobre critérios contábeis e de provisionamento aplicáveis às instituições abrangidas pela norma. O QuitaCalc utiliza parâmetros e estimativas para simular cenários; não é uma ferramenta oficial do Banco Central e não representa o cálculo, a política ou a oferta de qualquer instituição financeira."
  2. "Os resultados são estimativas informativas, calculadas com base nos dados fornecidos e nos critérios adotados pela ferramenta. Não constituem proposta oficial, promessa de desconto, garantia de redução da dívida, parecer jurídico, contábil ou financeiro, nem asseguram que determinada condição será oferecida ou aceita."
  3. "Somente a instituição financeira credora pode analisar, validar, apresentar e aceitar uma proposta de negociação, de acordo com suas políticas, os dados do contrato e as circunstâncias de cada caso. Uma simulação do QuitaCalc não obriga a instituição financeira a conceder desconto, renegociar a dívida ou aceitar qualquer valor."
  4. "Os cálculos e as estimativas podem não refletir todos os elementos do contrato, encargos, atualizações, políticas internas ou circunstâncias específicas da dívida. O usuário deve conferir as informações diretamente com a instituição financeira e, quando necessário, buscar orientação profissional."
- nota: "Nunca envie senhas bancárias, dados de cartão, códigos de autenticação ou informações de acesso à conta. O QuitaCalc não substitui orientação jurídica, contábil ou financeira quando necessária."

### CTA final
- título: "Pronto para negociar com mais informação?"
- texto: "Adquira seu acesso ao QuitaCalc por R$ 97,00." (valor de `preco.atual`)
- botão: "Preencher cadastro" (rola até o cadastro)

### Obrigado (`/obrigado`)
- título: "Pagamento recebido. Obrigado!"
- texto: "Em até 24 horas você receberá no e-mail cadastrado as orientações de acesso ao QuitaCalc e o tutorial de uso. Se tiver qualquer dúvida, fale com a gente pelo WhatsApp."
- botão: "Falar no WhatsApp"

### Rodapé
- aviso: "As simulações do QuitaCalc são estimativas informativas. Não constituem oferta ou garantia de negociação; a aceitação depende exclusivamente da instituição financeira."

### Política de Privacidade e Termos
Criar as duas páginas só para o QuitaCalc, usando o texto atual como base: coleta de nome, e-mail e WhatsApp para identificar a compra e enviar o acesso; pagamento processado pelo Asaas; formulário de apoio; direitos do titular (LGPD); contato do controlador (`operador`). Remover qualquer menção a parceria jurídica e aos serviços da Facilitare.

FIM DO PROMPT

---

## Depois de aplicar

1. Conferir que `src/content/quitacalc.ts` existe e contém todos os textos.
2. Procurar no código por "jurídic", "parceria", "grupofacilitare" e "facilitare.com.br": só pode sobrar o nome do logo, se ele tiver "Facilitare".
3. Fazer uma compra de teste: cadastro → Asaas → `/obrigado`, e conferir que os campos UTM ficaram gravados.
4. Conectar o domínio próprio em Settings → Domains.
5. Preencher `rastreamento` com os IDs das contas de anúncio do QuitaCalc (separadas das da Facilitare).
6. Preencher os campos marcados `[CONFIRMAR]`, principalmente a política de reembolso.
