# Script 1 — Site institucional Facilitare (B2B)

**Onde usar:** no projeto Lovable atual do site (hoje em grupofacilitare.com.br).
**Domínio final:** www.facilitare.com.br
**Como usar:** copie tudo a partir de "INÍCIO DO PROMPT" e cole no chat do Lovable. Se o Lovable cortar por tamanho, envie a Parte A numa mensagem e a Parte B na seguinte.

---

INÍCIO DO PROMPT

## PARTE A — Regras (não pular)

Vamos reestruturar o conteúdo deste site. O visual atual está aprovado e **não pode mudar**.

### 1. O que NÃO alterar

- Não altere cores, tokens de tema, `index.css`, configuração do Tailwind nem o modo claro/escuro.
  - Referência (manter exatamente): fundo `oklch(100% 0 0)`, texto `oklch(18.61% .0294 259.81)`, primária `oklch(74.03% .1559 235.89)`, destaque `oklch(62.31% .188 259.81)`; no escuro, fundo `oklch(18.61% .0294 259.81)` e texto branco.
- Não altere as fontes: **Sora** nos títulos, **Inter** no texto.
- Não altere o logo (`logo-facilitare-dark.png` e variações), o favicon, nem a posição e o tamanho do logo no cabeçalho.
- Não altere o layout do cabeçalho, do rodapé, os espaçamentos, os raios de borda, as sombras, os botões nem os cards.
- Para as páginas novas, **reutilize os componentes e seções que já existem** (hero, cards de solução, lista com check, seção "Como trabalhamos", faixa de CTA, rodapé). Nada de estilo novo.
- Não invente depoimentos, clientes, logos de clientes, números de resultado nem prêmios.

### 2. Conteúdo editável (obrigatório)

- Todo o texto do site deve ficar em **um único arquivo**: `src/content/site.ts`, exportando um objeto tipado `site`.
- Os componentes e páginas leem desse arquivo. **Nenhum texto fixo dentro do JSX**: títulos, parágrafos, itens de lista, botões, links, WhatsApp, e-mail, endereço, CNPJ, textos do rodapé e SEO por página (title e description).
- Coloque um comentário `// EDITÁVEL` acima de cada bloco e use nomes de campo em português (`titulo`, `subtitulo`, `itens`, `botao`, `ativo`).
- Listas (soluções, dores, etapas, cases, equipe) devem ser arrays. Acrescentar ou remover um item no array deve acrescentar ou remover o card na tela, sem mexer em componente.
- Blocos opcionais têm `ativo: true/false`. Quando `ativo: false` ou a lista estiver vazia, a seção não aparece e o item some do menu.
- Os valores entre `[CONFIRMAR]` devem ir exatamente assim para o arquivo, para eu revisar depois.

### 3. O que remover do site

- Remova **todo** o conteúdo sobre QuitaCalc, dívidas bancárias, simulação, parceria jurídica e pessoas físicas: seções da home, itens de menu, textos do rodapé (os dois avisos legais), mensagens de WhatsApp desses assuntos e opções do formulário de contato.
- Apague as páginas `/quitacalc`, `/parceiros-juridicos` e `/faq`. Essas três rotas devem redirecionar para `/` (redirecionamento no roteador, com `replace`).
- O site não terá FAQ nem seção de perguntas frequentes.
- Não coloque nenhum link para o QuitaCalc em nenhuma página.

### 4. Domínio e SEO técnico

- URL canônica: `https://www.facilitare.com.br` (campo `site.seo.urlBase`, editável).
- Cada página com `title`, `meta description`, `og:title`, `og:description` e `link rel="canonical"` vindos de `site.ts`.
- Atualize `sitemap.xml` e `robots.txt` para o novo domínio e para as rotas novas. Tire as rotas removidas.
- Adicione dados estruturados JSON-LD do tipo `Organization` (nome, url, logo, e-mail, telefone, endereço) lidos de `site.ts`.
- Mantenha o conteúdo renderizado no HTML como já está hoje.

### 5. Formulário de contato que registra o pedido

- Substitua o formulário atual (que só abre o e-mail do visitante) por um que **salva o pedido** no Lovable Cloud.
- Tabela `leads`: `id`, `created_at`, `nome`, `empresa`, `email`, `telefone`, `porte` (opcional), `assunto`, `mensagem`, `pagina_origem`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`.
- Segurança: RLS ativado, visitante anônimo só pode **inserir**; leitura apenas para usuário autenticado.
- Capture os parâmetros UTM da primeira visita (guardar em `sessionStorage`) e envie junto com o pedido.
- Depois de enviar, mostre a mensagem de sucesso de `site.contato.formulario.sucesso` e o botão de WhatsApp.
- Checkbox obrigatório de consentimento com link para a Política de Privacidade.

### 6. Rotas finais

`/` · `/solucoes` · `/solucoes/marketing` · `/solucoes/seo` · `/solucoes/indicadores` · `/solucoes/fabrica-de-software` · `/solucoes/automacao-de-processos` · `/informativo` · `/projetos` (só aparece se houver cases ativos) · `/quem-somos` · `/contato` · `/politica-de-privacidade` · `/termos-de-uso`

**Menu:** Início · Soluções (submenu com as 5 soluções) · Informativo · Projetos (se ativo) · Quem Somos · Contato. Botão do cabeçalho: "Pedir diagnóstico" → `/contato`.

**Rodapé:** mesmo layout de hoje, com navegação, contato, endereço, CNPJ `[CONFIRMAR]`, links de Política e Termos e o texto "© {ano} Facilitare. Todos os direitos reservados." Sem avisos de QuitaCalc ou jurídico.

**Modelo de página de solução** (um componente só, alimentado por `site.solucoes[]`): hero (rótulo, título, subtítulo, 2 botões) → "Para quem é" (lista) → "O que entregamos" (cards com título e descrição) → "Como funciona" (etapas) → "Formas de contratar" (cards) → "Exemplo" (opcional, `ativo`) → faixa de CTA com WhatsApp de mensagem própria. Sem FAQ.

## PARTE B — Conteúdo inicial de `src/content/site.ts`

Use exatamente estes textos.

### Geral

- marca: "Facilitare"
- assinatura: "Mais clareza para decidir. Mais inteligência para resolver."
- whatsapp: "5511916064145"
- email: "comercial@facilitare.com.br [CONFIRMAR]"
- endereço: "Alameda Terracota, 185, Conj. 1213, Cerâmica, São Caetano do Sul – SP, CEP 09531-190"
- cnpj: "[CONFIRMAR]"
- linkedin: "" (se vazio, não mostrar)
- SEO da home: title "Facilitare — Marketing, SEO, indicadores e automação para empresas"; description "Marketing digital, SEO, painéis de indicadores, software sob medida e automação de processos para empresas que querem crescer com clareza."

### Home (`/`)

**Hero**
- rótulo: "Marketing, SEO, indicadores e automação para empresas"
- título: "Mais clientes encontrando você. Mais clareza para decidir."
- subtítulo: "Cuidamos do marketing digital e do SEO da sua empresa, medimos o que traz resultado com painéis de indicadores e tiramos do manual os processos que tomam o tempo da equipe, com soluções feitas sob medida."
- botão 1: "Pedir diagnóstico gratuito" → `/contato`
- botão 2: "Conhecer as soluções" → `/solucoes`
- No cartão lateral do hero (onde hoje está "Visão integrada"), manter as 4 etapas: Entender o cenário · Organizar informações · Construir a solução · Acompanhar a evolução.

**Seção "Dores que resolvemos"**
- título: "Qual destes desafios parece com o da sua empresa?"
- cards (texto → link):
  1. "Nosso site não aparece no Google." → SEO
  2. "Investimos em marketing e não sabemos o que dá retorno." → Indicadores
  3. "Os contatos chegam e se perdem no caminho." → Marketing
  4. "A equipe passa o dia copiando dados de um lugar para outro." → Automação de processos
  5. "Nenhum sistema pronto serve para o nosso processo." → Fábrica de Software
  6. "Não temos tempo de acompanhar mercado e concorrência." → Informativo

**Seção "Soluções"**
- título: "Soluções para empresas"
- subtítulo: "Cada solução começa pelo entendimento do seu contexto e termina com algo que você consegue medir."
- 5 cards, um por solução, com título, frase curta e link "Saiba mais" (textos abaixo).

**Seção Informativo (destaque)**
- rótulo: "Produto"
- título: "Informativo: o que importa para o seu negócio, todo dia, no seu e-mail."
- texto: "Monitoramos notícias, órgãos oficiais e fontes do seu setor, resumimos com inteligência artificial e entregamos uma newsletter revisada, com a marca da sua empresa."
- botão: "Conhecer o Informativo" → `/informativo`

**Seção "Como trabalhamos"** (manter a seção atual, uma vez só)
1. Entender — "Ouvimos o contexto, as necessidades e os objetivos."
2. Organizar — "Estruturamos dados, processos e informações relevantes."
3. Construir — "Desenvolvemos a solução adequada ao desafio."
4. Acompanhar — "Medimos os resultados e apoiamos os próximos passos."

**Seção "Formas de contratar"**
- "Diagnóstico gratuito" — "Uma conversa para entender o desafio e indicar o melhor caminho, sem compromisso."
- "Projeto com escopo fechado" — "Entregas, prazo e valor combinados antes do início."
- "Plano mensal" — "Acompanhamento contínuo de SEO, marketing, indicadores e sustentação de sistemas."

**Seção Projetos** (`ativo: false` até haver cases)

**CTA final**
- título: "Vamos entender o seu desafio?"
- texto: "Conte o que você precisa. Em uma conversa curta, indicamos um caminho possível, com clareza sobre prazo e investimento."
- botões: "Pedir diagnóstico gratuito" → `/contato` e "Falar no WhatsApp".

### Soluções (`site.solucoes[]`)

Cada solução tem: `slug`, `titulo`, `frase` (card da home), `hero.titulo`, `hero.subtitulo`, `paraQuem[]`, `entregas[] {titulo, descricao}`, `etapas[]`, `contratacao[]`, `exemplo {ativo, titulo, texto}`, `whatsappMensagem`, `seo {title, description}`.

**1. Marketing** — `/solucoes/marketing`
- frase: "Planejamento, conteúdo e páginas que transformam visitas em contatos."
- hero: "Marketing que gera contatos e mostra o retorno." / "Planejamos, produzimos e medimos as ações de marketing digital da sua empresa, para que cada real investido tenha resultado visível."
- para quem: "Empresas que investem em marketing sem saber o retorno"; "Empresas que recebem contatos mas perdem no caminho"; "Equipes sem tempo para produzir conteúdo"
- entregas:
  - Diagnóstico de marketing — "Presença digital, canais, concorrentes e funil atual, com prioridades claras."
  - Planejamento e posicionamento — "Público, mensagem, canais e calendário do trimestre."
  - Conteúdo para site e LinkedIn — "Pautas ligadas às buscas do seu cliente, produzidas com apoio de IA e revisão humana."
  - Sites e páginas de conversão — "Páginas com formulário que registra cada contato e avisa a sua equipe."
  - Campanhas pagas `[CONFIRMAR]` — "Google Ads e Meta Ads com acompanhamento de custo por contato."
- etapas: "Diagnóstico" · "Plano" · "Execução" · "Medição mensal"
- contratação: Projeto com escopo fechado · Plano mensal
- whatsapp: "Olá! Quero conversar sobre o marketing da minha empresa."
- seo: "Marketing digital para empresas | Facilitare" / "Planejamento, conteúdo, páginas de conversão e medição de resultados para empresas."

**2. SEO** — `/solucoes/seo`
- frase: "Sua empresa encontrada por quem já está procurando o que você vende."
- hero: "Apareça no Google para quem procura o que você oferece." / "Ajustamos seu site, pesquisamos o que seus clientes buscam e acompanhamos as posições mês a mês."
- para quem: "Empresas com site que não aparece nas buscas"; "Negócios que dependem de clientes da região"; "Empresas que querem depender menos de anúncio pago"
- entregas:
  - Auditoria técnica — "Indexação, velocidade, estrutura das páginas, dados estruturados e erros no Search Console."
  - Palavras-chave e conteúdo — "Pesquisa do que seu cliente busca, otimização das páginas e plano de novos conteúdos."
  - SEO local — "Google Perfil da Empresa, avaliações e presença nas buscas da sua região."
  - Acompanhamento mensal — "Posições, visitas vindas do Google e contatos gerados, em painel e relatório."
- etapas: "Auditoria" · "Correções" · "Conteúdo" · "Acompanhamento"
- contratação: Projeto de auditoria e correções · Plano mensal
- whatsapp: "Olá! Quero que minha empresa apareça melhor no Google."
- seo: "SEO para empresas | Facilitare" / "Auditoria técnica, palavras-chave, SEO local e acompanhamento mensal de posições."

**3. Indicadores** — `/solucoes/indicadores`
- frase: "Painéis que mostram o que está funcionando, sem planilha montada à mão."
- hero: "Dados organizados. Decisões mais claras." / "Organizamos as informações da sua empresa e criamos painéis de indicadores que se atualizam sozinhos."
- para quem: "Empresas que montam relatórios à mão todo mês"; "Áreas que discordam sobre qual é o número certo"; "Gestores que querem acompanhar metas em um só lugar"
- entregas:
  - Painel de marketing e vendas — "Origem dos contatos, custo por contato, conversão por etapa e receita por canal."
  - Painéis de gestão — "Financeiro, operação, metas e análises como curva ABC."
  - Organização de bases e CRM — "Limpeza, remoção de duplicados e padronização de cadastros e listas."
  - Relatórios automáticos — "O relatório chega pronto por e-mail na data combinada."
- etapas: "Levantamento das fontes" · "Organização dos dados" · "Painel" · "Acompanhamento"
- contratação: Projeto com escopo fechado · Plano mensal
- whatsapp: "Olá! Quero conversar sobre os dados e indicadores da minha empresa."
- seo: "Painéis de indicadores e dashboards | Facilitare" / "Organização de dados, dashboards de marketing, vendas e gestão, e relatórios automáticos."

**4. Fábrica de Software** — `/solucoes/fabrica-de-software`
- frase: "Sistemas sob medida para o jeito que a sua empresa trabalha."
- hero: "Software feito para o seu processo, não o contrário." / "Desenvolvemos sistemas web sob medida, com inteligência artificial onde ela ajuda de verdade, e cuidamos deles depois da entrega."
- para quem: "Empresas cujo processo não cabe em sistema pronto"; "Quem atende vários clientes e precisa de uma plataforma própria"; "Empresas que querem usar IA com custo sob controle"
- entregas:
  - Sistemas web sob medida — "Login, perfis de acesso e histórico de quem fez o quê."
  - Plataformas multiempresa — "Cada cliente com seus dados separados, sua marca e suas configurações."
  - IA com custo controlado — "Resumo, classificação e triagem de textos, com orçamento e limite diário de uso."
  - Hospedagem e sustentação — "Manutenção, correções e melhorias contínuas por mensalidade."
- etapas: "Entendimento do processo" · "Protótipo" · "Desenvolvimento" · "Sustentação"
- contratação: Projeto com escopo fechado · Sustentação mensal
- exemplo (`ativo: true`): título "Informativo", texto "Plataforma multiempresa desenvolvida e operada pela Facilitare, com captação de fontes, curadoria com IA e envio de newsletters."
- whatsapp: "Olá! Quero conversar sobre um sistema sob medida para minha empresa."
- seo: "Fábrica de software sob medida | Facilitare" / "Sistemas web sob medida, plataformas multiempresa e IA aplicada com custo controlado."

**5. Automação de processos** — `/solucoes/automacao-de-processos`
- frase: "Soluções simples e personalizadas para tirar a rotina do manual."
- hero: "Do manual para o automático, uma rotina por vez." / "Identificamos as tarefas repetitivas que tomam o tempo da sua equipe e criamos soluções simples, feitas sob medida, para que elas aconteçam sozinhas."
- para quem: "Equipes que copiam dados entre planilhas e sistemas"; "Pedidos e aprovações que chegam por e-mail e WhatsApp"; "Relatórios e documentos montados à mão"
- entregas:
  - Mapeamento da rotina — "Entendemos o passo a passo atual e estimamos as horas economizadas antes de construir."
  - Da planilha para um sistema simples — "Controles em planilha viram uma tela com cadastro, busca e histórico."
  - Formulários, pedidos e aprovações — "Solicitações passam por um fluxo organizado e ficam registradas."
  - Integrações e avisos automáticos — "Formulários, e-mail, CRM e planilhas conectados, sem digitação duplicada."
  - Documentos e envios automáticos — "Relatórios, e-mails e documentos gerados e enviados na data certa."
- etapas: "Mapear" · "Simplificar" · "Automatizar" · "Medir o tempo economizado"
- contratação: Projeto pequeno por rotina · Plano mensal de melhorias
- whatsapp: "Olá! Quero automatizar um processo manual da minha empresa."
- seo: "Automação de processos para empresas | Facilitare" / "Soluções simples e sob medida para automatizar rotinas manuais, formulários, aprovações e relatórios."

### Soluções (`/solucoes`)
- título: "Soluções para empresas"
- subtítulo: "Marketing, SEO, indicadores, software e automação. Você pode começar por uma e somar as outras quando fizer sentido."
- grade com os 5 cards + CTA final.

### Informativo (`/informativo`)
- hero: rótulo "Produto" · título "O que importa para o seu negócio, todo dia, no seu e-mail." · subtítulo "O Informativo monitora fontes de notícias, órgãos oficiais e do seu setor, resume com inteligência artificial e entrega uma newsletter revisada, com a marca da sua empresa." · botão "Quero conhecer" (WhatsApp: "Olá! Quero conhecer o Informativo.")
- recursos:
  - Monitoramento de fontes — "Veículos de notícia, órgãos oficiais e fontes do seu setor, com fontes exclusivas para a sua empresa."
  - Curadoria com IA — "Captação, remoção de repetidos e prioridade por tema. Uma pessoa revisa antes do envio."
  - Newsletter com a sua marca — "Nome, cor, logo e assunto do e-mail definidos pela sua empresa."
  - Painel e controle de custos — "Indicadores de uso, custo por notícia e perfis de acesso para a equipe."
- para quem: "Empresas que precisam acompanhar mercado, regulação e concorrência"; "Empresas que querem enviar conteúdo relevante para clientes e parceiros"
- contratação: "Assinatura mensal"

### Quem Somos (`/quem-somos`)
- Manter a estrutura atual (título, "Nossa atuação", 6 princípios, CTA).
- Trocar o 2º parágrafo de "Nossa atuação" por: "Atendemos empresas que querem ser encontradas por mais clientes, entender seus números e tirar do manual os processos que tomam tempo da equipe."
- Nova seção "Quem faz" com `site.equipe[]` (`nome`, `cargo`, `foto`, `linkedin`, `bio`), `ativo: false` até eu preencher.

### Contato (`/contato`)
- título: "Vamos conversar sobre o que sua empresa precisa?"
- subtítulo: "Preencha o formulário ou chame no WhatsApp. Respondemos em até 1 dia útil. [CONFIRMAR]"
- campos: Nome* · Empresa* · E-mail* · Telefone/WhatsApp* · Porte (1–10, 11–50, 51–200, mais de 200 funcionários) · Assunto* (Marketing, SEO, Indicadores, Fábrica de Software, Automação de processos, Informativo, Outro) · Mensagem*
- sucesso: "Recebemos seu pedido. Vamos entrar em contato em breve."
- aviso: "Não envie senhas ou dados de acesso por este formulário."

### Política de Privacidade e Termos
Manter as páginas, trocar a marca para "Facilitare" e o domínio para www.facilitare.com.br, e remover qualquer trecho sobre QuitaCalc, compra, pagamento, simulação ou parceria jurídica.

FIM DO PROMPT

---

## Depois de aplicar

1. Conferir no Lovable: `src/content/site.ts` existe e contém todos os textos.
2. Procurar no código por "QuitaCalc", "jurídic", "dívida" e "Asaas": não deve sobrar nenhum resultado.
3. Publicar e, em Settings → Domains, conectar www.facilitare.com.br. Manter grupofacilitare.com.br redirecionando para o novo domínio.
4. No Google Search Console: adicionar o novo domínio, enviar o `sitemap.xml` e usar "Mudança de endereço" a partir do domínio antigo.
5. Preencher os campos marcados `[CONFIRMAR]`.
