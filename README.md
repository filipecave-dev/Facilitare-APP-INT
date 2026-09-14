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
| `INFORMATIVO_DSN`             | DSN do banco (padrão `sqlite:///output/informativo.db`) |
| `INFORMATIVO_SECRET_KEY`      | Chave da sessão Flask (defina em produção)       |
| `INFORMATIVO_ADMIN_PASSWORD`  | Senha do admin para `create-admin`               |
| `INFORMATIVO_USER_PASSWORD`   | Senha para `create-user`                         |

## Deploy no Render

O repositório já traz o `render.yaml` (blueprint), `wsgi.py` (entrypoint
gunicorn) e `Procfile`. Passo a passo:

1. No [Render](https://render.com): **New +** → **Blueprint** → conecte este
   repositório e selecione a branch. O Render lê o `render.yaml`.
2. Em **Environment**, defina o valor de **`INFORMATIVO_ADMIN_PASSWORD`**
   (mínimo 8 caracteres). As demais variáveis já vêm configuradas:
   - `INFORMATIVO_SECRET_KEY` — gerada automaticamente pelo Render.
   - `INFORMATIVO_ADMIN_USERNAME` — `admin` (ajuste se quiser).
3. **Create** / **Deploy**. Na primeira subida o sistema cria as tabelas,
   semeia as 80 fontes e cria o usuário admin a partir das variáveis acima.
4. Acesse a URL pública (`https://informativo.onrender.com`) e faça login.

Comandos usados pelo Render (já no blueprint):

```bash
# build
pip install -r requirements.txt && pip install .
# start
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
```

### Persistência dos dados

No **plano free** o disco é efêmero: a cada novo deploy (ou reinício por
inatividade) o SQLite é recriado — as 80 fontes e o admin voltam
automaticamente, mas fontes adicionadas manualmente, alterações de tema e
usuários extras se perdem. Para manter tudo, use um **disco persistente**
(plano pago): descomente o bloco `disk:` no `render.yaml`, troque o plano para
`starter` e aponte `INFORMATIVO_DSN` para
`sqlite:////var/data/informativo.db`.

> Para uma alternativa sem disco, o núcleo já isola o acesso a dados em
> `db.py`; migrar para Postgres (Render Postgres) é o caminho natural numa
> próxima iteração.

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Perfis de acesso

- **Administrador** — acesso total, incluindo gestão de fontes.
- **Editor** — cria/edita/remove fontes e monta newsletters.
- **Auditor** — acesso somente leitura (consulta, sem alterar cadastros).
