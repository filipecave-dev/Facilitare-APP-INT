"""Aplicação web (Flask) do InformaTivoli.

Interface visual com login/senha e as telas descritas na especificação do
produto. Nesta versão estão totalmente funcionais:

* **Autenticação** — login contra a tabela ``usuarios`` (hash PBKDF2).
* **Painel Principal** — visão geral do cadastro de fontes.
* **Gerenciar Fontes** — listar, filtrar, adicionar, importar, ativar/desativar
  e remover as fontes de informação (semeadas a partir da aba *Fontes* da
  planilha de referência).
* **Configurações** — seletor de tema/cores (padrão azul, ao estilo QuitaCalc)
  e chaves de integração (e-mail e Omniroute).

As demais telas da especificação (Criar Newsletter, Preparo do Texto, Editor de
Layout, Auditoria e Parceiros) estão presentes como *placeholders* navegáveis,
prontas para receberem implementação nas próximas iterações.

Fábrica principal: :func:`create_app`.
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Optional

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..auth import PERFIS, UsuarioRepository
from ..db import Database, init_db
from ..fontes import FonteRepository
from ..settings_repo import SettingsRepository
from ..themes import CHAVE_TEMA, PRESETS, TEMA_PADRAO, normalizar_cor, variaveis_css

DSN_PADRAO = "sqlite:///output/informativoli.db"


def create_app(dsn: Optional[str] = None) -> Flask:
    app = Flask(__name__)
    app.config["DSN"] = dsn or os.environ.get("INFORMATIVOLI_DSN", DSN_PADRAO)
    app.secret_key = os.environ.get("INFORMATIVOLI_SECRET_KEY") or os.urandom(32)

    # Garante o esquema, semeia as fontes e (em ambientes sem shell, como o
    # Render) cria o administrador a partir de variáveis de ambiente.
    with Database(app.config["DSN"]) as db:
        init_db(db)
        FonteRepository(db).semear_se_vazio()
        _bootstrap_admin(db)

    _registrar(app)
    return app


def _bootstrap_admin(db: Database) -> None:
    """Cria o admin inicial a partir de env vars, se ainda não houver usuários.

    Útil para deploys sem terminal interativo (ex.: Render): defina
    ``INFORMATIVOLI_ADMIN_PASSWORD`` (e opcionalmente
    ``INFORMATIVOLI_ADMIN_USERNAME`` / ``INFORMATIVOLI_ADMIN_NOME``) e o usuário
    é criado automaticamente na primeira subida. Não faz nada se já existir
    algum usuário ou se a senha não estiver definida.
    """
    repo = UsuarioRepository(db)
    if repo.count() > 0:
        return
    senha = os.environ.get("INFORMATIVOLI_ADMIN_PASSWORD")
    if not senha or len(senha) < 8:
        return
    username = os.environ.get("INFORMATIVOLI_ADMIN_USERNAME", "admin")
    nome = os.environ.get("INFORMATIVOLI_ADMIN_NOME", "Administrador")
    try:
        repo.criar(username, senha, "Administrador", nome=nome)
    except ValueError:
        # Corrida entre workers do gunicorn: outro processo já criou.
        pass


# ---------------------------------------------------------------------------
# Conexão por requisição
# ---------------------------------------------------------------------------
def _db() -> Database:
    if "db" not in g:
        g.db = Database(_app_dsn())
    return g.db


def _app_dsn() -> str:
    from flask import current_app

    return current_app.config["DSN"]


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
def _principal():
    """Conta do usuário logado (ou ``None``)."""
    username = session.get("username")
    if not username:
        return None
    return UsuarioRepository(_db()).get(username)


def login_obrigatorio(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def perfil_obrigatorio(*perfis: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            principal = _principal()
            if principal is None:
                return redirect(url_for("login"))
            if principal.perfil not in perfis:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return deco


# ---------------------------------------------------------------------------
# Registro de rotas
# ---------------------------------------------------------------------------
def _registrar(app: Flask) -> None:

    @app.teardown_appcontext
    def _fechar_db(_exc=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.context_processor
    def _injetar_globais():
        principal = _principal()
        cor = SettingsRepository(_db()).get(CHAVE_TEMA, TEMA_PADRAO)
        return {
            "principal": principal,
            "tema_css_vars": variaveis_css(cor),
            "PERFIS": PERFIS,
        }

    # -- Autenticação -------------------------------------------------------
    @app.route("/", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "")
            senha = request.form.get("senha", "")
            conta = UsuarioRepository(_db()).autenticar(username, senha)
            if conta is None:
                flash("Usuário ou senha inválidos.", "erro")
                return redirect(url_for("login"))
            session["username"] = conta.username
            session["nome"] = conta.nome or conta.username
            flash(f"Bem-vindo(a), {session['nome']}!", "ok")
            return redirect(url_for("dashboard"))
        if session.get("username"):
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sessão encerrada.", "ok")
        return redirect(url_for("login"))

    # -- Painel principal ---------------------------------------------------
    @app.route("/dashboard")
    @login_obrigatorio
    def dashboard():
        repo = FonteRepository(_db())
        resumo = repo.resumo()
        recentes = repo.listar()[:8]
        return render_template("dashboard.html", resumo=resumo, recentes=recentes)

    # -- Gerenciar fontes ---------------------------------------------------
    @app.route("/fontes")
    @login_obrigatorio
    def fontes():
        repo = FonteRepository(_db())
        busca = request.args.get("busca") or None
        categoria = request.args.get("categoria") or None
        regiao = request.args.get("regiao") or None
        apenas_ativas = request.args.get("ativas") == "1"
        lista = repo.listar(
            busca=busca,
            categoria=categoria,
            regiao=regiao,
            apenas_ativas=apenas_ativas,
        )
        return render_template(
            "fontes.html",
            fontes=lista,
            categorias=repo.categorias(),
            regioes=repo.regioes(),
            filtros={
                "busca": busca or "",
                "categoria": categoria or "",
                "regiao": regiao or "",
                "ativas": apenas_ativas,
            },
            resumo=repo.resumo(),
        )

    @app.route("/fontes/adicionar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_adicionar():
        repo = FonteRepository(_db())
        try:
            fonte = repo.criar(
                request.form.get("nome", ""),
                request.form.get("url", ""),
                categoria=request.form.get("categoria") or None,
                regiao=request.form.get("regiao") or None,
                idioma=request.form.get("idioma") or None,
                relevancia=int(request.form.get("relevancia", 3) or 3),
                prioridade=int(request.form.get("prioridade", 3) or 3),
                ativa=request.form.get("ativa", "1") == "1",
            )
            flash(f"Fonte '{fonte.nome}' adicionada.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("fontes"))

    @app.route("/fontes/<int:fonte_id>/alternar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_alternar(fonte_id: int):
        FonteRepository(_db()).alternar_ativa(fonte_id)
        return redirect(request.referrer or url_for("fontes"))

    @app.route("/fontes/<int:fonte_id>/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_remover(fonte_id: int):
        repo = FonteRepository(_db())
        fonte = repo.get(fonte_id)
        if fonte is None:
            abort(404)
        repo.remover(fonte_id)
        flash(f"Fonte '{fonte.nome}' removida.", "ok")
        return redirect(url_for("fontes"))

    @app.route("/fontes/importar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_importar():
        from ..fontes import carregar_seed

        repo = FonteRepository(_db())
        resultado = repo.importar(carregar_seed())
        flash(
            "Importação concluída: "
            f"{resultado['inseridas']} nova(s), "
            f"{resultado['ignoradas']} já existia(m).",
            "ok",
        )
        return redirect(url_for("fontes"))

    # -- Configurações (tema + integrações) ---------------------------------
    @app.route("/settings", methods=["GET", "POST"])
    @login_obrigatorio
    def settings():
        repo = SettingsRepository(_db())
        if request.method == "POST":
            cor = normalizar_cor(request.form.get("tema_primary", TEMA_PADRAO))
            repo.set(CHAVE_TEMA, cor)
            repo.set("api_email", request.form.get("api_email", "").strip())
            repo.set("api_omniroute", request.form.get("api_omniroute", "").strip())
            flash("Configurações salvas.", "ok")
            return redirect(url_for("settings"))
        return render_template(
            "settings.html",
            presets=PRESETS,
            cor_atual=repo.get(CHAVE_TEMA, TEMA_PADRAO),
            api_email=repo.get("api_email", ""),
            api_omniroute=repo.get("api_omniroute", ""),
        )

    # -- Placeholders navegáveis (próximas iterações) -----------------------
    _pagina_em_construcao(app, "newsletter_nova", "/newsletter/new", "Criar Newsletter")
    _pagina_em_construcao(app, "newsletter_preparo", "/newsletter/prepare", "Preparo do Texto")
    _pagina_em_construcao(app, "layout", "/layout", "Editor de Layout")
    _pagina_em_construcao(app, "auditoria", "/audit", "Auditoria")
    _pagina_em_construcao(app, "parceiros", "/partners", "Parceiros")

    # -- Erros --------------------------------------------------------------
    @app.errorhandler(403)
    def _erro_403(_e):
        return render_template("403.html"), 403


def _pagina_em_construcao(app: Flask, endpoint: str, rota: str, titulo: str) -> None:
    """Registra uma rota de placeholder navegável ('em construção')."""

    @login_obrigatorio
    def view(_titulo=titulo):
        return render_template("em_construcao.html", titulo=_titulo)

    app.add_url_rule(rota, endpoint, view)
