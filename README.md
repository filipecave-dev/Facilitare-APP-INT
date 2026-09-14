# Informativo

Sistema para **gestão de informações capturadas em diversos provedores
(fontes)**. Faz parte da suíte Facilitare e segue o mesmo padrão visual do
QuitaCalc (Flask + Jinja + CSS, com tema por variáveis CSS e **cor padrão
azul**).

O cadastro inicial de fontes é semeado a partir da aba **Fontes** da planilha
de referência (80 provedores: veículos de notícias, órgãos oficiais, blogs de
aviação, saúde, segurança e fenômenos naturais).

## Status desta versão (v0.1)

Totalmente funcional:

- **Autenticação** — login/senha com hash PBKDF2, perfis Administrador, Editor
  e Auditor.
- **Painel Principal** — visão geral do cadastro de fontes.
- **Gerenciar Fontes** — listar, filtrar (busca, categoria, região, ativas),
  adicionar, importar em massa, ativar/desativar e remover. Semeado com as 80
  fontes da planilha.
- **Empresas (Clientes)** — cadastro das empresas que usam a solução. Cada
  empresa é um cliente e personaliza o seu **nome da solução** (como o
  informativo é chamado para aquele cliente) e o **assunto do e-mail** que sai
  para os seus destinatários, além de e-mail de contato e cor de destaque
  própria.
- **Configurações** — seletor de tema/cores (presets + cor personalizada,
  padrão azul) e chaves de integração (E-mail e Omniroute), persistidas para
  uso futuro.

Telas previstas na especificação, presentes como *placeholders* navegáveis
(próximas iterações): **Criar Newsletter**, **Preparo do Texto**, **Editor de
Layout** e **Auditoria**.

## Arquitetura

```
src/informativo/
├── db.py             # camada fina sobre sqlite3 + esquema
├── auth.py           # contas de usuário e autenticação (PBKDF2)
├── fontes.py         # cadastro de fontes (CRUD, filtros, importação, seed)
├── empresas.py       # cadastro de empresas/clientes (nome de saída, cor)
├── settings_repo.py  # configurações chave/valor (tema, integrações)
├── themes.py         # paletas de tema (padrão azul) e derivação de CSS
├── seed_data/
│   └── fontes_seed.json   # 80 fontes da aba "Fontes" da planilha
└── web/
    ├── __init__.py   # create_app + rotas (Flask)
    ├── cli.py        # create-admin / create-user / run
    ├── static/style.css
    └── templates/*.html
```

O núcleo (db, auth, fontes, settings, themes) depende apenas da biblioteca
padrão + Werkzeug; Flask é usado somente pela camada web.

## Como executar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 1) Crie o usuário administrador (a senha nunca fica no código)
export INFORMATIVO_ADMIN_PASSWORD='sua-senha-forte'
informativo-web create-admin --dsn sqlite:///output/informativo.db

# 2) Suba o servidor (as 80 fontes são semeadas na primeira execução)
export INFORMATIVO_SECRET_KEY='uma-chave-secreta-forte'
informativo-web run --dsn sqlite:///output/informativo.db --port 8000
```

Acesse http://127.0.0.1:8000 e faça login.

### Criar outros usuários

```bash
export INFORMATIVO_USER_PASSWORD='senha-do-usuario'
informativo-web create-user --username editor --perfil Editor
informativo-web create-user --username auditoria --perfil Auditor
```

## Variáveis de ambiente

| Variável                        | Descrição                                        |
|---------------------------------|--------------------------------------------------|
| `INFORMATIVO_DSN`             | DSN do banco: `sqlite:///arquivo.db` ou `postgresql://usuario:senha@host/banco` |
| `INFORMATIVO_SECRET_KEY`      | Chave da sessão Flask (defina em produção)       |
| `INFORMATIVO_ADMIN_PASSWORD`  | Senha do admin para `create-admin`               |
| `INFORMATIVO_USER_PASSWORD`   | Senha para `create-user`                         |

## Deploy no Render

O repositório já traz o `render.yaml` (blueprint), `wsgi.py` (entrypoint
gunicorn) e `Procfile`. Passo a passo:

1. No [Render](https://render.com): **New +** → **Blueprint** → conecte este
   repositório e selecione a branch. O Render lê o `render.yaml` e provisiona
   **um banco PostgreSQL gratuito** (`informativo-db`) + o serviço web.
2. Em **Environment**, opcionalmente defina **`INFORMATIVO_ADMIN_PASSWORD`**
   (mín. 8 caracteres) para o admin ser recriado a cada deploy. As demais já
   vêm configuradas:
   - `INFORMATIVO_SECRET_KEY` — gerada automaticamente pelo Render.
   - `INFORMATIVO_DSN` — preenchida automaticamente com a URL do PostgreSQL.
3. **Apply** / **Deploy**. Na primeira subida o sistema cria as tabelas e
   semeia as 80 fontes no PostgreSQL.
4. Acesse a URL pública (`https://centralinformativo.onrender.com`). Se ainda
   não houver admin, você cai na tela de **primeiro acesso** (`/setup`) para
   criá-lo pelo navegador; depois é só logar.

Comandos usados pelo Render (já no blueprint):

```bash
# build
pip install -r requirements.txt && pip install .
# start
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
```

### Persistência dos dados (PostgreSQL)

O banco é escolhido pelo `INFORMATIVO_DSN`:

- **SQLite** (`sqlite:///...`) — padrão local, para desenvolvimento e testes.
- **PostgreSQL** (`postgresql://...`) — usado em produção. O `render.yaml`
  provisiona um **Postgres gratuito do Render** e liga a URL automaticamente,
  de modo que **usuários, senhas, fontes, empresas e tema persistem entre
  deploys**.

> O Postgres gratuito do Render tem limite de armazenamento e o plano free
> expira ~30 dias após a criação. Como o app aceita qualquer URL
> `postgresql://`, migrar depois para um provedor sem expiração (ex.: Neon,
> Supabase) é só trocar o valor de `INFORMATIVO_DSN`.

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Perfis de acesso

- **Administrador** — acesso total, incluindo gestão de fontes.
- **Editor** — cria/edita/remove fontes e monta newsletters.
- **Auditor** — acesso somente leitura (consulta, sem alterar cadastros).
