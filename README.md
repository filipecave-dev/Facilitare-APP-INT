# InformaTivoli

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
- **Configurações** — seletor de tema/cores (presets + cor personalizada,
  padrão azul) e chaves de integração (E-mail e Omniroute), persistidas para
  uso futuro.

Telas previstas na especificação, presentes como *placeholders* navegáveis
(próximas iterações): **Criar Newsletter**, **Preparo do Texto**, **Editor de
Layout**, **Auditoria** e **Parceiros**.

## Arquitetura

```
src/informativoli/
├── db.py             # camada fina sobre sqlite3 + esquema
├── auth.py           # contas de usuário e autenticação (PBKDF2)
├── fontes.py         # cadastro de fontes (CRUD, filtros, importação, seed)
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
export INFORMATIVOLI_ADMIN_PASSWORD='sua-senha-forte'
informativoli-web create-admin --dsn sqlite:///output/informativoli.db

# 2) Suba o servidor (as 80 fontes são semeadas na primeira execução)
export INFORMATIVOLI_SECRET_KEY='uma-chave-secreta-forte'
informativoli-web run --dsn sqlite:///output/informativoli.db --port 8000
```

Acesse http://127.0.0.1:8000 e faça login.

### Criar outros usuários

```bash
export INFORMATIVOLI_USER_PASSWORD='senha-do-usuario'
informativoli-web create-user --username editor --perfil Editor
informativoli-web create-user --username auditoria --perfil Auditor
```

## Variáveis de ambiente

| Variável                        | Descrição                                        |
|---------------------------------|--------------------------------------------------|
| `INFORMATIVOLI_DSN`             | DSN do banco (padrão `sqlite:///output/informativoli.db`) |
| `INFORMATIVOLI_SECRET_KEY`      | Chave da sessão Flask (defina em produção)       |
| `INFORMATIVOLI_ADMIN_PASSWORD`  | Senha do admin para `create-admin`               |
| `INFORMATIVOLI_USER_PASSWORD`   | Senha para `create-user`                         |

## Deploy no Render

O repositório já traz o `render.yaml` (blueprint), `wsgi.py` (entrypoint
gunicorn) e `Procfile`. Passo a passo:

1. No [Render](https://render.com): **New +** → **Blueprint** → conecte este
   repositório e selecione a branch. O Render lê o `render.yaml`.
2. Em **Environment**, defina o valor de **`INFORMATIVOLI_ADMIN_PASSWORD`**
   (mínimo 8 caracteres). As demais variáveis já vêm configuradas:
   - `INFORMATIVOLI_SECRET_KEY` — gerada automaticamente pelo Render.
   - `INFORMATIVOLI_ADMIN_USERNAME` — `admin` (ajuste se quiser).
3. **Create** / **Deploy**. Na primeira subida o sistema cria as tabelas,
   semeia as 80 fontes e cria o usuário admin a partir das variáveis acima.
4. Acesse a URL pública (`https://informativoli.onrender.com`) e faça login.

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
`starter` e aponte `INFORMATIVOLI_DSN` para
`sqlite:////var/data/informativoli.db`.

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
