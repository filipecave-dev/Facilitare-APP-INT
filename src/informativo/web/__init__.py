"""Aplicação web (Flask) do Informativo.

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
from ..empresas import EmpresaRepository
from ..fontes import FonteRepository
from ..settings_repo import SettingsRepository
from ..themes import CHAVE_TEMA, PRESETS, TEMA_PADRAO, normalizar_cor, variaveis_css

DSN_PADRAO = "sqlite:///output/informativo.db"


def create_app(dsn: Optional[str] = None) -> Flask:
    app = Flask(__name__)
    app.config["DSN"] = dsn or os.environ.get("INFORMATIVO_DSN", DSN_PADRAO)
    app.secret_key = os.environ.get("INFORMATIVO_SECRET_KEY") or os.urandom(32)

    # Garante o esquema, semeia as fontes e (em ambientes sem shell, como o
    # Render) cria o administrador a partir de variáveis de ambiente.
    with Database(app.config["DSN"]) as db:
        init_db(db)
        FonteRepository(db).semear_se_vazio()
        _bootstrap_admin(db)

    _registrar(app)
    return app


def _bootstrap_admin(db: Database) -> None:
    """Garante o usuário administrador a partir de variáveis de ambiente.

    Pensado para deploys sem terminal interativo (ex.: Render). Se
    ``INFORMATIVO_ADMIN_PASSWORD`` estiver definida (mín. 8 caracteres), o admin
    é **criado ou tem a senha atualizada** em toda subida — assim, definir a
    variável no painel e redeployar sempre destrava o login. As mensagens vão
    para o log (visível no Render) para facilitar o diagnóstico.

    Variáveis:
    - ``INFORMATIVO_ADMIN_PASSWORD`` (obrigatória p/ criar o admin, >= 8 chars)
    - ``INFORMATIVO_ADMIN_USERNAME`` (padrão ``admin``)
    - ``INFORMATIVO_ADMIN_NOME`` (padrão ``Administrador``)
    """
    repo = UsuarioRepository(db)
    senha = os.environ.get("INFORMATIVO_ADMIN_PASSWORD")
    username = os.environ.get("INFORMATIVO_ADMIN_USERNAME", "admin")
    nome = os.environ.get("INFORMATIVO_ADMIN_NOME", "Administrador")

    if not senha or len(senha) < 8:
        if repo.count() == 0:
            print(
                "[Informativo] AVISO: nenhum usuário cadastrado e "
                "INFORMATIVO_ADMIN_PASSWORD ausente ou com menos de 8 "
                "caracteres — o admin NÃO foi criado. Defina a variável no "
                "painel (>= 8 caracteres) e faça um novo deploy."
            )
        return

    try:
        # atualizar_se_existir garante que a env var seja a fonte de verdade
        # da senha do admin a cada subida (cria na 1ª vez, atualiza depois).
        repo.criar(username, senha, "Administrador", nome=nome, atualizar_se_existir=True)
        print(f"[Informativo] Admin garantido: username={username.strip().lower()!r}.")
    except ValueError as exc:
        print(f"[Informativo] Falha ao garantir o admin: {exc}")


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
        repo = UsuarioRepository(_db())
        # Primeiro acesso: nenhum usuário cadastrado -> tela de criação do admin.
        if repo.count() == 0:
            return redirect(url_for("setup"))
        if request.method == "POST":
            username = request.form.get("username", "")
            senha = request.form.get("senha", "")
            conta = repo.autenticar(username, senha)
            if conta is None:
                usuarios = [u.username for u in repo.listar()]
                print(
                    "[Informativo] Login FALHOU para "
                    f"username={username.strip().lower()!r} "
                    f"(senha com {len(senha)} caracteres). "
                    f"Usuários cadastrados: {usuarios}."
                )
                flash("Usuário ou senha inválidos.", "erro")
                return redirect(url_for("login"))
            session["username"] = conta.username
            session["nome"] = conta.nome or conta.username
            flash(f"Bem-vindo(a), {session['nome']}!", "ok")
            return redirect(url_for("dashboard"))
        if session.get("username"):
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        """Primeiro acesso: cria o administrador pelo navegador.

        Só funciona enquanto não houver nenhum usuário cadastrado; depois
        disso, redireciona para o login. Isso garante o acesso mesmo sem
        variáveis de ambiente configuradas.
        """
        repo = UsuarioRepository(_db())
        if repo.count() > 0:
            return redirect(url_for("login"))
        if request.method == "POST":
            username = (request.form.get("username") or "admin").strip()
            senha = request.form.get("senha", "")
            confirmar = request.form.get("confirmar", "")
            nome = (request.form.get("nome") or "Administrador").strip()
            if len(senha) < 8:
                flash("A senha deve ter ao menos 8 caracteres.", "erro")
                return redirect(url_for("setup"))
            if senha != confirmar:
                flash("As senhas não conferem.", "erro")
                return redirect(url_for("setup"))
            try:
                conta = repo.criar(username, senha, "Administrador", nome=nome)
            except ValueError as exc:
                flash(str(exc), "erro")
                return redirect(url_for("setup"))
            session["username"] = conta.username
            session["nome"] = conta.nome or conta.username
            flash("Administrador criado com sucesso. Bem-vindo(a)!", "ok")
            return redirect(url_for("dashboard"))
        return render_template("setup.html")

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
        total_empresas = EmpresaRepository(_db()).count()
        return render_template(
            "dashboard.html",
            resumo=resumo,
            recentes=recentes,
            total_empresas=total_empresas,
        )

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

    # -- Configurações (tema + e-mail) --------------------------------------
    @app.route("/settings", methods=["GET", "POST"])
    @login_obrigatorio
    def settings():
        repo = SettingsRepository(_db())
        if request.method == "POST":
            cor = normalizar_cor(request.form.get("tema_primary", TEMA_PADRAO))
            repo.set(CHAVE_TEMA, cor)
            repo.set("api_email", request.form.get("api_email", "").strip())
            flash("Configurações salvas.", "ok")
            return redirect(url_for("settings"))
        return render_template(
            "settings.html",
            presets=PRESETS,
            cor_atual=repo.get(CHAVE_TEMA, TEMA_PADRAO),
            api_email=repo.get("api_email", ""),
        )

    # -- Provedores de IA (conexões: OmniRoute/GPT/DeepSeek/Gemini/Claude) --
    @app.route("/provedores")
    @perfil_obrigatorio("Administrador")
    def provedores():
        from ..provedores import ProvedorRepository

        return render_template(
            "provedores.html",
            provedores=ProvedorRepository(_db()).listar(),
            empresas=EmpresaRepository(_db()).listar(),
        )

    @app.route("/provedores/criar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def provedores_criar():
        from ..provedores import ProvedorRepository

        try:
            empresa_id = request.form.get("empresa_id") or None
            empresa_id = int(empresa_id) if empresa_id else None
            p = ProvedorRepository(_db()).criar(
                request.form.get("nome", ""),
                request.form.get("formato", "openai"),
                request.form.get("base_url", ""),
                request.form.get("modelo", ""),
                api_key=request.form.get("api_key") or None,
                empresa_id=empresa_id,
                ativo=request.form.get("ativo", "1") == "1",
            )
            flash(f"Provedor '{p.nome}' cadastrado.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("provedores"))

    @app.route("/provedores/<int:pid>/editar", methods=["GET", "POST"])
    @perfil_obrigatorio("Administrador")
    def provedores_editar(pid: int):
        from ..provedores import ProvedorRepository

        repo = ProvedorRepository(_db())
        p = repo.get(pid)
        if p is None:
            abort(404)
        if request.method == "POST":
            emp = request.form.get("empresa_id") or None
            campos = {
                "nome": request.form.get("nome", p.nome),
                "formato": request.form.get("formato", p.formato),
                "base_url": request.form.get("base_url", p.base_url),
                "modelo": request.form.get("modelo", p.modelo),
                "empresa_id": int(emp) if emp else None,
                "ativo": request.form.get("ativo", "1") == "1",
            }
            # Chave só é trocada se o campo vier preenchido.
            nova_chave = (request.form.get("api_key") or "").strip()
            if nova_chave:
                campos["api_key"] = nova_chave
            try:
                repo.atualizar(pid, **campos)
                flash("Provedor atualizado.", "ok")
                return redirect(url_for("provedores"))
            except ValueError as exc:
                flash(str(exc), "erro")
        return render_template(
            "provedor_editar.html",
            p=repo.get(pid),
            empresas=EmpresaRepository(_db()).listar(),
        )

    @app.route("/provedores/<int:pid>/alternar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def provedores_alternar(pid: int):
        from ..provedores import ProvedorRepository

        ProvedorRepository(_db()).alternar_ativo(pid)
        return redirect(url_for("provedores"))

    @app.route("/provedores/<int:pid>/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def provedores_remover(pid: int):
        from ..provedores import ProvedorRepository

        ProvedorRepository(_db()).remover(pid)
        flash("Provedor removido.", "ok")
        return redirect(url_for("provedores"))

    @app.route("/provedores/<int:pid>/testar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def provedores_testar(pid: int):
        from ..provedores import IAError, ProvedorRepository

        p = ProvedorRepository(_db()).get(pid)
        if p is None:
            abort(404)
        try:
            resposta = p.cliente(timeout=30).chat("Responda apenas: OK", max_tokens=10)
            flash(f"'{p.nome}' respondeu: {resposta[:120]}", "ok")
        except IAError as exc:
            flash(f"Falha em '{p.nome}': {exc}", "erro")
        return redirect(url_for("provedores"))

    # -- Captação + triagem -------------------------------------------------
    @app.route("/captacao")
    @login_obrigatorio
    def captacao():
        from ..omniroute import CaptacaoRepository
        from ..provedores import ProvedorRepository

        status = request.args.get("status") or "pendente"
        repo_cap = CaptacaoRepository(_db())
        repo_fontes = FonteRepository(_db())
        return render_template(
            "captacao.html",
            captacoes=repo_cap.listar_recentes(80, status=status),
            contagem=repo_cap.contar_por_status(),
            status_atual=status,
            provedores=ProvedorRepository(_db()).listar(apenas_ativos=True),
            empresas=EmpresaRepository(_db()).listar(),
            regioes=repo_fontes.regioes(),
            total_ativas=repo_fontes.resumo()["ativas"],
        )

    @app.route("/captacao/rodar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_rodar():
        from ..omniroute import CaptacaoRepository, prompt_para_fonte
        from ..provedores import IAError, ProvedorRepository

        try:
            quantidade = int(request.form.get("quantidade", 5))
        except (TypeError, ValueError):
            quantidade = 5
        quantidade = max(1, min(15, quantidade))

        provedor = None
        pid = request.form.get("provedor_id")
        if pid:
            provedor = ProvedorRepository(_db()).get(int(pid))
        if provedor is None or not provedor.ativo:
            flash("Selecione um provedor de IA ativo (cadastre em Provedores).", "erro")
            return redirect(url_for("captacao"))

        cli = provedor.cliente()
        repo_fontes = FonteRepository(_db())
        repo_cap = CaptacaoRepository(_db())
        # Foco por região. Padrão: nacional (Brasil) primeiro.
        regiao = request.form.get("regiao", "__BR__")
        fontes = repo_fontes.listar(apenas_ativas=True)
        if regiao == "__BR__":
            fontes = [f for f in fontes if "brasil" in (f.regiao or "").lower()]
        elif regiao:
            fontes = [f for f in fontes if f.regiao == regiao]
        fontes = fontes[:quantidade]
        if not fontes:
            flash("Nenhuma fonte ativa para o foco selecionado.", "aviso")
            return redirect(url_for("captacao"))
        ok = falhas = 0
        primeiro_erro = None
        for fonte in fontes:
            system, prompt = prompt_para_fonte(fonte)
            try:
                texto = cli.chat(prompt, system=system)
                repo_cap.registrar(fonte, texto, provedor=provedor.nome)
                ok += 1
            except IAError as exc:
                falhas += 1
                if primeiro_erro is None:
                    primeiro_erro = str(exc)
        if ok:
            flash(f"Captação concluída via '{provedor.nome}': {ok} fonte(s).", "ok")
        if falhas:
            flash(
                f"{falhas} fonte(s) falharam. Primeiro erro: {primeiro_erro}",
                "erro" if not ok else "aviso",
            )
        return redirect(url_for("captacao"))

    @app.route("/captacao/<int:cid>/<acao>", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_status(cid: int, acao: str):
        from ..omniroute import CaptacaoRepository

        mapa = {"aprovar": "aprovada", "descartar": "descartada", "pendente": "pendente"}
        if acao not in mapa:
            abort(404)
        CaptacaoRepository(_db()).definir_status(cid, mapa[acao])
        return redirect(request.referrer or url_for("captacao"))

    # -- Empresas (clientes) ------------------------------------------------
    @app.route("/empresas")
    @login_obrigatorio
    def empresas():
        repo = EmpresaRepository(_db())
        return render_template("empresas.html", empresas=repo.listar())

    @app.route("/empresas/adicionar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresas_adicionar():
        repo = EmpresaRepository(_db())
        try:
            empresa = repo.criar(
                request.form.get("nome", ""),
                nome_solucao=request.form.get("nome_solucao") or None,
                assunto_email=request.form.get("assunto_email") or None,
                contato_email=request.form.get("contato_email") or None,
                tema_primary=normalizar_cor(request.form.get("tema_primary", TEMA_PADRAO)),
                ativa=request.form.get("ativa", "1") == "1",
            )
            flash(f"Empresa '{empresa.nome}' cadastrada.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("empresas"))

    @app.route("/empresas/<int:empresa_id>", methods=["GET", "POST"])
    @login_obrigatorio
    def empresa_editar(empresa_id: int):
        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        if request.method == "POST":
            principal = _principal()
            if principal is None or principal.perfil != "Administrador":
                abort(403)
            try:
                repo.atualizar(
                    empresa_id,
                    nome=request.form.get("nome", empresa.nome),
                    nome_solucao=request.form.get("nome_solucao", ""),
                    assunto_email=request.form.get("assunto_email", ""),
                    contato_email=request.form.get("contato_email") or None,
                    tema_primary=normalizar_cor(
                        request.form.get("tema_primary", empresa.tema_primary or TEMA_PADRAO)
                    ),
                    ativa=request.form.get("ativa", "1") == "1",
                )
                flash("Empresa atualizada.", "ok")
                return redirect(url_for("empresas"))
            except ValueError as exc:
                flash(str(exc), "erro")
        return render_template(
            "empresa_editar.html", empresa=empresa, presets=PRESETS
        )

    @app.route("/empresas/<int:empresa_id>/alternar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresas_alternar(empresa_id: int):
        EmpresaRepository(_db()).alternar_ativa(empresa_id)
        return redirect(request.referrer or url_for("empresas"))

    @app.route("/empresas/<int:empresa_id>/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresas_remover(empresa_id: int):
        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        repo.remover(empresa_id)
        flash(f"Empresa '{empresa.nome}' removida.", "ok")
        return redirect(url_for("empresas"))

    # -- Usuários (gestão de acesso pelo administrador) ---------------------
    @app.route("/usuarios")
    @perfil_obrigatorio("Administrador")
    def usuarios():
        contas = UsuarioRepository(_db()).listar()
        return render_template("usuarios.html", contas=contas)

    @app.route("/usuarios/criar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_criar():
        repo = UsuarioRepository(_db())
        username = request.form.get("username", "")
        senha = request.form.get("senha", "")
        nome = request.form.get("nome") or None
        perfil = request.form.get("perfil", "Editor")
        if len(senha) < 8:
            flash("A senha deve ter ao menos 8 caracteres.", "erro")
            return redirect(url_for("usuarios"))
        try:
            conta = repo.criar(username, senha, perfil, nome=nome)
            flash(f"Usuário '{conta.username}' criado (perfil {conta.perfil}).", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("usuarios"))

    @app.route("/usuarios/alternar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_alternar():
        repo = UsuarioRepository(_db())
        username = (request.form.get("username") or "").strip().lower()
        principal = _principal()
        if principal and username == principal.username:
            flash("Você não pode desativar a sua própria conta.", "erro")
            return redirect(url_for("usuarios"))
        conta = repo.get(username)
        if conta is None:
            abort(404)
        repo.set_ativo(username, not conta.ativo)
        flash(
            f"Usuário '{username}' {'ativado' if not conta.ativo else 'desativado'}.",
            "ok",
        )
        return redirect(url_for("usuarios"))

    @app.route("/usuarios/senha", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_senha():
        repo = UsuarioRepository(_db())
        username = (request.form.get("username") or "").strip().lower()
        nova = request.form.get("senha", "")
        if repo.get(username) is None:
            abort(404)
        if len(nova) < 8:
            flash("A nova senha deve ter ao menos 8 caracteres.", "erro")
            return redirect(url_for("usuarios"))
        repo.redefinir_senha(username, nova)
        flash(f"Senha de '{username}' redefinida.", "ok")
        return redirect(url_for("usuarios"))

    @app.route("/usuarios/perfil", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_perfil():
        repo = UsuarioRepository(_db())
        username = (request.form.get("username") or "").strip().lower()
        perfil = request.form.get("perfil", "Editor")
        if repo.get(username) is None:
            abort(404)
        try:
            repo.definir_perfil(username, perfil)
            flash(f"Perfil de '{username}' atualizado para {perfil}.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("usuarios"))

    # -- Placeholders navegáveis (próximas iterações) -----------------------
    _pagina_em_construcao(app, "newsletter_nova", "/newsletter/new", "Criar Newsletter")
    _pagina_em_construcao(app, "newsletter_preparo", "/newsletter/prepare", "Preparo do Texto")
    _pagina_em_construcao(app, "layout", "/layout", "Editor de Layout")
    _pagina_em_construcao(app, "auditoria", "/audit", "Auditoria")

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
