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

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Perfis de acesso

- **Administrador** — acesso total, incluindo gestão de fontes.
- **Editor** — cria/edita/remove fontes e monta newsletters.
- **Auditor** — acesso somente leitura (consulta, sem alterar cadastros).
