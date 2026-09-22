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
    Response,
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
        # Ajuste único: desativa todas as fontes existentes uma vez (a ativação
        # passa a ser decisão explícita do operador). Guardado por flag para
        # não repetir e não sobrescrever ativações futuras.
        sett = SettingsRepository(db)
        if sett.get("fontes_desativadas_inicial") != "1":
            FonteRepository(db).definir_ativa_em_massa(False)
            sett.set("fontes_desativadas_inicial", "1")
        # Backfill único: preenche o RSS das fontes existentes a partir da
        # semente (feeds descobertos). Roda uma vez.
        if sett.get("fontes_rss_backfill") != "1":
            FonteRepository(db).backfill_rss_da_semente()
            sett.set("fontes_rss_backfill", "1")
        # Ativação única: as fontes globais com RSS entram ativas por padrão.
        if sett.get("fontes_rss_ativadas") != "1":
            FonteRepository(db).ativar_com_rss_global()
            sett.set("fontes_rss_ativadas", "1")
        # Marca a data de início do plano gratuito do banco (Render). Na 1ª vez
        # define hoje; e uma correção única alinha à data real em que o banco
        # foi provisionado no Render. O Administrador pode reajustar depois em
        # Configurações.
        from ..plano import CFG_DB_INICIO, DATA_INICIO_OPERACAO, garantir_inicio

        garantir_inicio(sett)
        # v2: reaplica com data+hora (o ajuste anterior gravou só a data).
        if sett.get("db_free_inicio_ajustado_v2") != "1":
            sett.set(CFG_DB_INICIO, DATA_INICIO_OPERACAO)
            sett.set("db_free_inicio_ajustado_v2", "1")
        # Ajuste único: conexões Gemini legadas passam a usar o modelo
        # econômico gemini-2.5-flash-lite.
        if sett.get("gemini_25_flash_lite") != "1":
            from ..provedores import ProvedorRepository

            ProvedorRepository(db).normalizar_modelo_gemini()
            sett.set("gemini_25_flash_lite", "1")
        # Ajuste único: garante a empresa "Tivolitur" e move o conteúdo atual
        # (captações ainda sem empresa) para ela.
        if sett.get("conteudo_atual_tivolitur") != "1":
            from ..omniroute import CaptacaoRepository

            emp = EmpresaRepository(db).obter_ou_criar(
                "Tivolitur", nome_solucao="Tivolitur"
            )
            CaptacaoRepository(db).atribuir_empresa_em_massa(emp.id)
            sett.set("conteudo_atual_tivolitur", "1")

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


def _is_plataforma(principal) -> bool:
    """True se a conta é da plataforma (acesso global, sem empresa)."""
    return principal is not None and principal.empresa_id is None


def plataforma_obrigatoria(fn):
    """Restringe a ação ao Administrador da Plataforma (recursos globais)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        principal = _principal()
        if principal is None:
            return redirect(url_for("login"))
        if principal.empresa_id is not None or principal.perfil != "Administrador":
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


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
            "impersonador": session.get("impersonador"),
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
        from ..omniroute import CaptacaoRepository
        from ..uso import Precos, UsoRepository

        principal = _principal()
        plataforma = _is_plataforma(principal)
        repo = FonteRepository(_db())
        cap_repo = CaptacaoRepository(_db())

        # Escopo: empresa vê só o seu; plataforma vê tudo e pode filtrar por
        # empresa cadastrada (?empresa_id=). Sem filtro, a plataforma vê o todo.
        if plataforma:
            eid = request.args.get("empresa_id") or None
            filtro_empresa = int(eid) if eid else None
            somente = filtro_empresa is not None
        else:
            filtro_empresa = principal.empresa_id
            somente = True

        m = cap_repo.metricas(empresa_id=filtro_empresa, somente_empresa=somente)
        uso_repo = UsoRepository(_db())
        uso = uso_repo.resumo_do_dia(
            Precos(SettingsRepository(_db())),
            empresa_id=filtro_empresa, somente_empresa=somente)
        abc = uso_repo.curva_abc(empresa_id=filtro_empresa, somente_empresa=somente)
        empresa = None
        empresa_alvo = filtro_empresa if plataforma else principal.empresa_id
        if empresa_alvo is not None:
            empresa = EmpresaRepository(_db()).get(empresa_alvo)
        # Regressivo do plano gratuito do banco — só para o Administrador da
        # plataforma (quem cuida da infraestrutura/migração ao plano pago).
        plano_bd = None
        if plataforma and principal.perfil == "Administrador":
            from ..plano import contagem_regressiva

            plano_bd = contagem_regressiva(SettingsRepository(_db()))
        return render_template(
            "dashboard.html",
            plano_bd=plano_bd,
            resumo=repo.resumo(),
            is_plataforma=plataforma,
            total_empresas=EmpresaRepository(_db()).count(),
            empresas=EmpresaRepository(_db()).listar() if plataforma else [],
            filtro_empresa=filtro_empresa,
            empresa=empresa,
            m=m,
            uso=uso,
            abc=abc,
            top_fontes=cap_repo.top_fontes(8, empresa_id=filtro_empresa, somente_empresa=somente),
            fontes_fracas=cap_repo.fontes_sem_relevancia(8, empresa_id=filtro_empresa, somente_empresa=somente),
            por_frente=cap_repo.por_frente(empresa_id=filtro_empresa, somente_empresa=somente),
            serie=cap_repo.serie_diaria(14, empresa_id=filtro_empresa, somente_empresa=somente),
        )

    # -- Gerenciar fontes (globais + privadas por empresa) ------------------
    def _pode_gerir_fonte(principal, fonte) -> bool:
        """Plataforma gere qualquer fonte; empresa só as suas privadas."""
        if _is_plataforma(principal):
            return True
        return fonte is not None and fonte.empresa_id == principal.empresa_id

    @app.route("/fontes")
    @login_obrigatorio
    def fontes():
        principal = _principal()
        repo = FonteRepository(_db())
        busca = request.args.get("busca") or None
        categoria = request.args.get("categoria") or None
        regiao = request.args.get("regiao") or None
        apenas_ativas = request.args.get("ativas") == "1"
        escopo = None if _is_plataforma(principal) else ("visiveis", principal.empresa_id)
        lista = repo.listar(
            busca=busca, categoria=categoria, regiao=regiao,
            apenas_ativas=apenas_ativas, escopo=escopo,
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
            is_plataforma=_is_plataforma(principal),
            minha_empresa=principal.empresa_id,
            pode_gerir=principal.perfil in ("Administrador", "Editor"),
        )

    @app.route("/fontes/adicionar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_adicionar():
        from ..fontes import CandidataRepository

        principal = _principal()
        repo = FonteRepository(_db())
        # Plataforma cria global; empresa cria PRIVADA (e vira candidata).
        empresa_id = None if _is_plataforma(principal) else principal.empresa_id
        try:
            fonte = repo.criar(
                request.form.get("nome", ""),
                request.form.get("url", ""),
                categoria=request.form.get("categoria") or None,
                regiao=request.form.get("regiao") or None,
                idioma=request.form.get("idioma") or None,
                rss=request.form.get("rss") or None,
                relevancia=int(request.form.get("relevancia", 3) or 3),
                prioridade=int(request.form.get("prioridade", 3) or 3),
                empresa_id=empresa_id,
                ativa=request.form.get("ativa", "1") == "1",
            )
            if empresa_id is not None:
                CandidataRepository(_db()).registrar(fonte)
                flash(f"Fonte privada '{fonte.nome}' adicionada (enviada para curadoria).", "ok")
            else:
                flash(f"Fonte global '{fonte.nome}' adicionada.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("fontes"))

    @app.route("/fontes/<int:fonte_id>/editar", methods=["GET", "POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_editar(fonte_id: int):
        repo = FonteRepository(_db())
        fonte = repo.get(fonte_id)
        if fonte is None:
            abort(404)
        if not _pode_gerir_fonte(_principal(), fonte):
            abort(403)
        if request.method == "POST":
            try:
                repo.atualizar(
                    fonte_id,
                    nome=request.form.get("nome", fonte.nome),
                    url=request.form.get("url", fonte.url),
                    categoria=request.form.get("categoria") or None,
                    regiao=request.form.get("regiao") or None,
                    idioma=request.form.get("idioma") or None,
                    rss=request.form.get("rss") or None,
                    relevancia=int(request.form.get("relevancia", fonte.relevancia) or 3),
                    prioridade=int(request.form.get("prioridade", fonte.prioridade) or 3),
                    ativa=request.form.get("ativa", "1") == "1",
                )
                flash("Fonte atualizada.", "ok")
                return redirect(url_for("fontes"))
            except ValueError as exc:
                flash(str(exc), "erro")
        return render_template(
            "fonte_editar.html",
            fonte=repo.get(fonte_id),
            categorias=repo.categorias(),
            regioes=repo.regioes(),
        )

    @app.route("/fontes/<int:fonte_id>/alternar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_alternar(fonte_id: int):
        repo = FonteRepository(_db())
        fonte = repo.get(fonte_id)
        if fonte is None:
            abort(404)
        if not _pode_gerir_fonte(_principal(), fonte):
            abort(403)
        repo.alternar_ativa(fonte_id)
        return redirect(request.referrer or url_for("fontes"))

    @app.route("/fontes/<int:fonte_id>/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_remover(fonte_id: int):
        repo = FonteRepository(_db())
        fonte = repo.get(fonte_id)
        if fonte is None:
            abort(404)
        if not _pode_gerir_fonte(_principal(), fonte):
            abort(403)
        repo.remover(fonte_id)
        flash(f"Fonte '{fonte.nome}' removida.", "ok")
        return redirect(url_for("fontes"))

    @app.route("/fontes/todas/<acao>", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def fontes_todas(acao: str):
        if acao not in ("ativar", "desativar"):
            abort(404)
        principal = _principal()
        # Plataforma opera o catálogo global; empresa, as próprias privadas.
        escopo = ("global",) if _is_plataforma(principal) else ("privadas", principal.empresa_id)
        FonteRepository(_db()).definir_ativa_em_massa(acao == "ativar", escopo=escopo)
        flash(
            "Todas as fontes " + ("ativadas." if acao == "ativar" else "desativadas."),
            "ok",
        )
        return redirect(url_for("fontes"))

    @app.route("/fontes/importar", methods=["POST"])
    @plataforma_obrigatoria
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

    # -- Curadoria de fontes (plataforma avalia as privadas sugeridas) ------
    @app.route("/curadoria")
    @plataforma_obrigatoria
    def curadoria():
        from ..fontes import CandidataRepository

        status = request.args.get("status") or "pendente"
        repo = CandidataRepository(_db())
        empresas = {e.id: e.nome for e in EmpresaRepository(_db()).listar()}
        return render_template(
            "curadoria.html",
            candidatas=repo.listar(status=status),
            status_atual=status,
            empresas=empresas,
        )

    @app.route("/curadoria/<int:cid>/promover", methods=["POST"])
    @plataforma_obrigatoria
    def curadoria_promover(cid: int):
        from ..fontes import CandidataRepository

        repo = CandidataRepository(_db())
        cand = repo.get(cid)
        if cand is None:
            abort(404)
        # Torna a fonte privada parte do catálogo global.
        if cand.get("fonte_id"):
            FonteRepository(_db()).promover_para_global(cand["fonte_id"])
        repo.definir_status(cid, "promovida")
        flash(f"Fonte '{cand.get('nome')}' promovida ao catálogo global.", "ok")
        return redirect(request.referrer or url_for("curadoria"))

    @app.route("/curadoria/<int:cid>/descartar", methods=["POST"])
    @plataforma_obrigatoria
    def curadoria_descartar(cid: int):
        from ..fontes import CandidataRepository

        repo = CandidataRepository(_db())
        if repo.get(cid) is None:
            abort(404)
        repo.definir_status(cid, "descartada")
        flash("Sugestão descartada.", "ok")
        return redirect(request.referrer or url_for("curadoria"))

    # -- Configurações (tema + e-mail) — globais da plataforma --------------
    @app.route("/settings", methods=["GET", "POST"])
    @plataforma_obrigatoria
    def settings():
        from ..uso import (
            CFG_LIMITE_DIA, CFG_MOEDA, CFG_PRECO_IN, CFG_PRECO_OUT, Precos,
        )

        repo = SettingsRepository(_db())
        if request.method == "POST":
            cor = normalizar_cor(request.form.get("tema_primary", TEMA_PADRAO))
            repo.set(CHAVE_TEMA, cor)
            repo.set("api_email", request.form.get("api_email", "").strip())
            # Orçamento de IA (preços por 1M tokens, moeda e teto diário).
            repo.set(CFG_PRECO_IN, (request.form.get("ia_preco_in", "") or "0").strip())
            repo.set(CFG_PRECO_OUT, (request.form.get("ia_preco_out", "") or "0").strip())
            repo.set(CFG_MOEDA, (request.form.get("ia_moeda", "") or "US$").strip())
            repo.set(CFG_LIMITE_DIA, (request.form.get("ia_limite_diario", "") or "0").strip())
            # Plano gratuito do banco (Render): data de início e total de dias.
            from ..plano import CFG_DB_DIAS, CFG_DB_INICIO

            di = (request.form.get("db_free_inicio", "") or "").strip()
            if di:
                repo.set(CFG_DB_INICIO, di)
            repo.set(CFG_DB_DIAS, (request.form.get("db_free_dias", "") or "30").strip())
            flash("Configurações salvas.", "ok")
            return redirect(url_for("settings"))
        from ..plano import contagem_regressiva

        return render_template(
            "settings.html",
            presets=PRESETS,
            cor_atual=repo.get(CHAVE_TEMA, TEMA_PADRAO),
            api_email=repo.get("api_email", ""),
            precos=Precos(repo),
            plano_bd=contagem_regressiva(repo),
        )

    # -- Provedores de IA (conexões: OmniRoute/GPT/DeepSeek/Gemini/Claude) --
    def _pode_gerir_provedor(principal, p) -> bool:
        """Plataforma gere tudo; empresa só os seus (nunca globais/de outra)."""
        if _is_plataforma(principal):
            return True
        return p is not None and p.empresa_id == principal.empresa_id

    def _selecionar_provedor(principal, pid=None):
        """Provedor de IA a usar: o escolhido (pid) ou o 1º ativo visível.

        Respeita o escopo: empresa só usa provedores globais ou os próprios.
        """
        from ..provedores import ProvedorRepository

        repo = ProvedorRepository(_db())
        if pid:
            p = repo.get(int(pid))
            if p and p.ativo and (_is_plataforma(principal) or p.empresa_id is None
                                  or p.empresa_id == principal.empresa_id):
                return p
        if _is_plataforma(principal):
            ativos = repo.listar(apenas_ativos=True)
        else:
            ativos = [p for p in repo.listar_visiveis(principal.empresa_id) if p.ativo]
        return ativos[0] if ativos else None

    @app.route("/provedores")
    @perfil_obrigatorio("Administrador", "Editor")
    def provedores():
        from ..provedores import ProvedorRepository

        principal = _principal()
        repo = ProvedorRepository(_db())
        if _is_plataforma(principal):
            lista = repo.listar()
            empresas = EmpresaRepository(_db()).listar()
        else:
            lista = repo.listar_visiveis(principal.empresa_id)
            empresas = []
        return render_template(
            "provedores.html",
            provedores=lista,
            empresas=empresas,
            is_plataforma=_is_plataforma(principal),
            minha_empresa=principal.empresa_id,
        )

    @app.route("/provedores/criar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def provedores_criar():
        from ..provedores import ProvedorRepository

        principal = _principal()
        if _is_plataforma(principal):
            emp = request.form.get("empresa_id") or None
            empresa_id = int(emp) if emp else None  # plataforma pode global
        else:
            empresa_id = principal.empresa_id  # empresa: sempre a própria
        try:
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
    @perfil_obrigatorio("Administrador", "Editor")
    def provedores_editar(pid: int):
        from ..provedores import ProvedorRepository

        principal = _principal()
        repo = ProvedorRepository(_db())
        p = repo.get(pid)
        if p is None:
            abort(404)
        if not _pode_gerir_provedor(principal, p):
            abort(403)
        if request.method == "POST":
            campos = {
                "nome": request.form.get("nome", p.nome),
                "formato": request.form.get("formato", p.formato),
                "base_url": request.form.get("base_url", p.base_url),
                "modelo": request.form.get("modelo", p.modelo),
                "ativo": request.form.get("ativo", "1") == "1",
            }
            # Só a plataforma reatribui empresa; empresa mantém a própria.
            if _is_plataforma(principal):
                emp = request.form.get("empresa_id") or None
                campos["empresa_id"] = int(emp) if emp else None
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
            empresas=EmpresaRepository(_db()).listar() if _is_plataforma(principal) else [],
            is_plataforma=_is_plataforma(principal),
        )

    @app.route("/provedores/<int:pid>/alternar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def provedores_alternar(pid: int):
        from ..provedores import ProvedorRepository

        repo = ProvedorRepository(_db())
        p = repo.get(pid)
        if p is None:
            abort(404)
        if not _pode_gerir_provedor(_principal(), p):
            abort(403)
        repo.alternar_ativo(pid)
        return redirect(url_for("provedores"))

    @app.route("/provedores/<int:pid>/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def provedores_remover(pid: int):
        from ..provedores import ProvedorRepository

        repo = ProvedorRepository(_db())
        p = repo.get(pid)
        if p is None:
            abort(404)
        if not _pode_gerir_provedor(_principal(), p):
            abort(403)
        repo.remover(pid)
        flash("Provedor removido.", "ok")
        return redirect(url_for("provedores"))

    @app.route("/provedores/<int:pid>/testar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def provedores_testar(pid: int):
        from ..provedores import IAError, ProvedorRepository

        principal = _principal()
        p = ProvedorRepository(_db()).get(pid)
        if p is None:
            abort(404)
        # Pode testar os que enxerga (globais ou da própria empresa).
        if not (_is_plataforma(principal) or p.empresa_id is None
                or p.empresa_id == principal.empresa_id):
            abort(403)
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
        from ..uso import Precos, UsoRepository

        principal = _principal()
        status = request.args.get("status") or "pendente"
        repo_cap = CaptacaoRepository(_db())
        repo_fontes = FonteRepository(_db())
        somente = not _is_plataforma(principal)  # empresa só vê as suas
        emp = principal.empresa_id
        # Provedores utilizáveis: ativos globais + os da empresa.
        prov_repo = ProvedorRepository(_db())
        if _is_plataforma(principal):
            provedores = prov_repo.listar(apenas_ativos=True)
        else:
            provedores = [p for p in prov_repo.listar_visiveis(emp) if p.ativo]
        return render_template(
            "captacao.html",
            captacoes=repo_cap.listar_recentes(80, status=status,
                                               empresa_id=emp, somente_empresa=somente),
            contagem=repo_cap.contar_por_status(empresa_id=emp, somente_empresa=somente),
            status_atual=status,
            provedores=provedores,
            empresas=EmpresaRepository(_db()).listar() if _is_plataforma(principal) else [],
            regioes=repo_fontes.regioes(),
            total_ativas=repo_fontes.resumo()["ativas"],
            frentes=CaptacaoRepository.FRENTES,
            uso_hoje=UsoRepository(_db()).resumo_do_dia(
                Precos(SettingsRepository(_db())),
                empresa_id=emp, somente_empresa=somente),
        )

    @app.route("/captacao/rodar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_rodar():
        from ..omniroute import CaptacaoRepository, prompt_para_fonte
        from ..provedores import IAError, ProvedorRepository
        from ..uso import Precos, UsoRepository, excede_limite

        try:
            quantidade = int(request.form.get("quantidade", 5))
        except (TypeError, ValueError):
            quantidade = 5
        quantidade = max(1, min(15, quantidade))

        principal = _principal()
        provedor = None
        pid = request.form.get("provedor_id")
        if pid:
            provedor = ProvedorRepository(_db()).get(int(pid))
        if provedor is None or not provedor.ativo:
            flash("Selecione um provedor de IA ativo (cadastre em Provedores).", "erro")
            return redirect(url_for("captacao"))
        # Empresa só usa provedores globais ou os da própria empresa.
        if not (_is_plataforma(principal) or provedor.empresa_id is None
                or provedor.empresa_id == principal.empresa_id):
            abort(403)

        cli = provedor.cliente()
        repo_fontes = FonteRepository(_db())
        repo_cap = CaptacaoRepository(_db())
        # Foco por região. Padrão: nacional (Brasil) primeiro.
        regiao = request.form.get("regiao", "__BR__")
        escopo = None if _is_plataforma(principal) else ("visiveis", principal.empresa_id)
        fontes = repo_fontes.listar(apenas_ativas=True, escopo=escopo)
        if regiao == "__BR__":
            fontes = [f for f in fontes if "brasil" in (f.regiao or "").lower()]
        elif regiao:
            fontes = [f for f in fontes if f.regiao == regiao]
        fontes = fontes[:quantidade]
        if not fontes:
            flash("Nenhuma fonte ativa para o foco selecionado.", "aviso")
            return redirect(url_for("captacao"))

        # Busca o conteúdo real da fonte (RSS/HTML) para a IA resumir fatos
        # atuais, quando marcado (padrão). Sem isso o resumo é genérico.
        buscar_conteudo = request.form.get("buscar_conteudo", "1") == "1"
        # Janela de datas: últimos N dias (padrão 5).
        try:
            dias = int(request.form.get("dias", 5))
        except (TypeError, ValueError):
            dias = 5
        dias = max(1, min(30, dias))

        # Teto diário de custo: trava a operação para não estourar o orçamento.
        precos = Precos(SettingsRepository(_db()))
        uso_repo = UsoRepository(_db())
        somente = not _is_plataforma(principal)
        if excede_limite(uso_repo, precos, empresa_id=principal.empresa_id,
                         somente_empresa=somente):
            flash(f"Limite diário de custo atingido ({precos.moeda} "
                  f"{precos.limite_diario:.2f}). Ajuste em Configurações.", "erro")
            return redirect(url_for("captacao"))

        ok = falhas = repetidas = 0
        limitado = False
        primeiro_erro = None
        for fonte in fontes:
            if excede_limite(uso_repo, precos, empresa_id=principal.empresa_id,
                             somente_empresa=somente):
                limitado = True
                break
            conteudo = ""
            if buscar_conteudo:
                from ..coleta import coletar_conteudo

                conteudo = coletar_conteudo(
                    fonte.url, feed_url=(fonte.rss or ""), dias=dias
                )
            system, prompt = prompt_para_fonte(fonte, conteudo, dias=dias)
            try:
                # Saída enxuta: economiza tokens a cada consulta.
                texto, uso = cli.chat_uso(prompt, system=system, max_tokens=380)
                custo = precos.custo(uso["in"], uso["out"])
                uso_repo.registrar("captura", uso, custo,
                                   empresa_id=principal.empresa_id, provedor=provedor.nome,
                                   fonte_id=fonte.id, fonte_nome=fonte.nome)
                novo = repo_cap.registrar(fonte, texto, provedor=provedor.nome,
                                          empresa_id=principal.empresa_id)
                if novo is None:
                    repetidas += 1
                else:
                    ok += 1
            except IAError as exc:
                falhas += 1
                if primeiro_erro is None:
                    primeiro_erro = str(exc)
        if ok:
            flash(f"Captação concluída via '{provedor.nome}': {ok} fonte(s).", "ok")
        if limitado:
            flash(f"Limite diário atingido ({precos.moeda} {precos.limite_diario:.2f}) "
                  "— captação interrompida. Ajuste em Configurações.", "aviso")
        if repetidas:
            flash(f"{repetidas} conteúdo(s) repetido(s) foram ignorados.", "aviso")
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
        repo = CaptacaoRepository(_db())
        cap = repo.get(cid)
        if cap is None:
            abort(404)
        principal = _principal()
        # Empresa só faz triagem das próprias captações.
        if not _is_plataforma(principal) and cap.get("empresa_id") != principal.empresa_id:
            abort(403)
        repo.definir_status(cid, mapa[acao])
        return redirect(request.referrer or url_for("captacao"))

    @app.route("/captacao/limpar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_limpar():
        """Limpa as captações (todas ou de um status), respeitando o escopo."""
        from ..omniroute import CaptacaoRepository

        principal = _principal()
        somente = not _is_plataforma(principal)
        status = request.form.get("status") or None
        if status and status not in CaptacaoRepository.STATUS:
            status = None
        n = CaptacaoRepository(_db()).limpar(
            status=status, empresa_id=principal.empresa_id, somente_empresa=somente
        )
        alvo = f"'{status}'" if status else "de todos os status"
        flash(f"{n} captação(ões) {alvo} removida(s).", "ok")
        return redirect(url_for("captacao", status=status or "pendente"))

    @app.route("/captacao/<int:cid>/frente", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_frente(cid: int):
        """Reclassifica (mesmo após aprovado) o conteúdo em uma das frentes."""
        from ..omniroute import CaptacaoRepository

        repo = CaptacaoRepository(_db())
        cap = repo.get(cid)
        if cap is None:
            abort(404)
        principal = _principal()
        if not _is_plataforma(principal) and cap.get("empresa_id") != principal.empresa_id:
            abort(403)
        frente = request.form.get("frente") or None
        try:
            repo.definir_frente(cid, frente)
            flash("Conteúdo reclassificado.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(request.referrer or url_for("captacao", status="aprovada"))

    @app.route("/captacao/<int:cid>/empresa", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_empresa(cid: int):
        """Define a empresa-destino do informativo (só a plataforma escolhe)."""
        from ..omniroute import CaptacaoRepository

        principal = _principal()
        if not _is_plataforma(principal):
            abort(403)  # empresa não reatribui suas captações
        repo = CaptacaoRepository(_db())
        if repo.get(cid) is None:
            abort(404)
        eid = request.form.get("empresa_id") or None
        empresa_id = int(eid) if eid else None
        repo.definir_empresa(cid, empresa_id)
        if empresa_id:
            emp = EmpresaRepository(_db()).get(empresa_id)
            flash(f"Encaminhado para '{emp.nome if emp else empresa_id}'.", "ok")
        else:
            flash("Empresa-destino removida (voltou para global).", "ok")
        return redirect(request.referrer or url_for("captacao"))

    @app.route("/captacao/atribuir", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_atribuir():
        """Atribui em massa as captações do status atual a uma empresa."""
        from ..omniroute import CaptacaoRepository

        principal = _principal()
        if not _is_plataforma(principal):
            abort(403)
        eid = request.form.get("empresa_id") or None
        if not eid:
            flash("Selecione a empresa-destino.", "erro")
            return redirect(url_for("captacao"))
        status = request.form.get("status") or None
        if status and status not in CaptacaoRepository.STATUS:
            status = None
        todas = request.form.get("todas") == "1"
        n = CaptacaoRepository(_db()).atribuir_empresa_em_massa(
            int(eid), status=status, apenas_sem_empresa=not todas
        )
        emp = EmpresaRepository(_db()).get(int(eid))
        flash(f"{n} captação(ões) encaminhada(s) para '{emp.nome if emp else eid}'.", "ok")
        return redirect(url_for("captacao", status=status or "pendente"))

    @app.route("/captacao/<int:cid>/parafrasear", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def captacao_parafrasear(cid: int):
        """Gera a paráfrase do item via IA conectada, para o informativo."""
        from ..omniroute import CaptacaoRepository, prompt_parafrase
        from ..provedores import IAError
        from ..uso import Precos, UsoRepository, excede_limite

        repo = CaptacaoRepository(_db())
        cap = repo.get(cid)
        if cap is None:
            abort(404)
        principal = _principal()
        if not _is_plataforma(principal) and cap.get("empresa_id") != principal.empresa_id:
            abort(403)
        provedor = _selecionar_provedor(principal, request.form.get("provedor_id"))
        if provedor is None:
            flash("Selecione um provedor de IA ativo para gerar a paráfrase.", "erro")
            return redirect(request.referrer or url_for("captacao", status="aprovada"))
        precos = Precos(SettingsRepository(_db()))
        uso_repo = UsoRepository(_db())
        somente = not _is_plataforma(principal)
        if excede_limite(uso_repo, precos, empresa_id=principal.empresa_id,
                         somente_empresa=somente):
            flash(f"Limite diário atingido ({precos.moeda} {precos.limite_diario:.2f}). "
                  "Ajuste em Configurações.", "erro")
            return redirect(request.referrer or url_for("captacao", status="aprovada"))
        nome_solucao = ""
        if cap.get("empresa_id"):
            emp = EmpresaRepository(_db()).get(cap["empresa_id"])
            nome_solucao = emp.nome_solucao if emp else ""
        system, prompt = prompt_parafrase(cap, nome_solucao=nome_solucao)
        try:
            texto, uso = provedor.cliente().chat_uso(prompt, system=system)
            uso_repo.registrar("parafrase", uso, precos.custo(uso["in"], uso["out"]),
                               empresa_id=cap.get("empresa_id"), provedor=provedor.nome,
                               fonte_id=cap.get("fonte_id"), fonte_nome=cap.get("fonte_nome"))
            repo.definir_parafrase(cid, texto)
            flash(f"Paráfrase gerada via '{provedor.nome}'.", "ok")
        except IAError as exc:
            flash(f"Falha ao gerar paráfrase: {exc}", "erro")
        return redirect(request.referrer or url_for("captacao", status="aprovada"))

    # -- Informativo (montagem automática a partir dos aprovados) -----------
    def _empresa_do_informativo(principal):
        """Resolve a empresa-alvo do informativo (query param p/ plataforma)."""
        if not _is_plataforma(principal):
            return EmpresaRepository(_db()).get(principal.empresa_id)
        eid = request.args.get("empresa_id") or request.form.get("empresa_id")
        if eid:
            return EmpresaRepository(_db()).get(int(eid))
        return None

    def _provedores_visiveis(principal):
        from ..provedores import ProvedorRepository

        repo = ProvedorRepository(_db())
        if _is_plataforma(principal):
            return repo.listar(apenas_ativos=True)
        return [p for p in repo.listar_visiveis(principal.empresa_id) if p.ativo]

    @app.route("/informativo")
    @login_obrigatorio
    def informativo():
        from ..empresas import familia_do_modelo
        from ..omniroute import CaptacaoRepository

        principal = _principal()
        somente = not _is_plataforma(principal)
        emp = principal.empresa_id
        empresa = _empresa_do_informativo(principal)
        alvo_emp = empresa.id if empresa else emp
        repo_cap = CaptacaoRepository(_db())
        aprovadas = repo_cap.listar_recentes(
            200, status="aprovada", empresa_id=alvo_emp,
            somente_empresa=somente or empresa is not None,
        )
        # Padrão unitário: cada notícia é um comunicado. O operador escolhe
        # quantos comunicados por página quer preparar/disparar.
        try:
            por_pagina = int(request.args.get("por_pagina", 1))
        except (TypeError, ValueError):
            por_pagina = 1
        por_pagina = max(1, min(20, por_pagina))
        try:
            pagina = int(request.args.get("pagina", 1))
        except (TypeError, ValueError):
            pagina = 1
        total = len(aprovadas)
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina = max(1, min(pagina, total_paginas))
        inicio = (pagina - 1) * por_pagina
        itens_pagina = aprovadas[inicio:inicio + por_pagina]
        familia = familia_do_modelo(empresa.fonte_modelo if empresa else None)
        return render_template(
            "informativo.html",
            empresa=empresa,
            itens=itens_pagina,
            total=total,
            por_pagina=por_pagina,
            pagina=pagina,
            total_paginas=total_paginas,
            inicio=inicio,
            familia_fonte=familia,
            empresas=EmpresaRepository(_db()).listar() if _is_plataforma(principal) else [],
            is_plataforma=_is_plataforma(principal),
            provedores=_provedores_visiveis(principal),
        )

    @app.route("/informativo/parafrasear-tudo", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def informativo_parafrasear_tudo():
        from ..empresas import familia_do_modelo  # noqa: F401
        from ..omniroute import CaptacaoRepository, prompt_parafrase
        from ..provedores import IAError
        from ..uso import Precos, UsoRepository, excede_limite

        principal = _principal()
        somente = not _is_plataforma(principal)
        empresa = _empresa_do_informativo(principal)
        alvo_emp = empresa.id if empresa else principal.empresa_id
        provedor = _selecionar_provedor(principal, request.form.get("provedor_id"))
        if provedor is None:
            flash("Selecione um provedor de IA ativo para gerar as paráfrases.", "erro")
            return redirect(url_for("informativo", empresa_id=alvo_emp))
        precos = Precos(SettingsRepository(_db()))
        uso_repo = UsoRepository(_db())
        if excede_limite(uso_repo, precos, empresa_id=principal.empresa_id,
                         somente_empresa=somente):
            flash(f"Limite diário atingido ({precos.moeda} {precos.limite_diario:.2f}). "
                  "Ajuste em Configurações.", "erro")
            return redirect(url_for("informativo", empresa_id=alvo_emp))
        repo = CaptacaoRepository(_db())
        aprovadas = repo.listar_recentes(
            200, status="aprovada", empresa_id=alvo_emp,
            somente_empresa=somente or empresa is not None,
        )
        cli = provedor.cliente()
        nome_solucao = empresa.nome_solucao if empresa else ""
        ok = falhas = 0
        limitado = False
        erro = None
        for c in aprovadas:
            if (c.get("parafrase") or "").strip():
                continue  # já parafraseado
            if excede_limite(uso_repo, precos, empresa_id=principal.empresa_id,
                             somente_empresa=somente):
                limitado = True
                break
            system, prompt = prompt_parafrase(c, nome_solucao=nome_solucao)
            try:
                texto, uso = cli.chat_uso(prompt, system=system)
                uso_repo.registrar("parafrase", uso, precos.custo(uso["in"], uso["out"]),
                                   empresa_id=c.get("empresa_id"), provedor=provedor.nome,
                                   fonte_id=c.get("fonte_id"), fonte_nome=c.get("fonte_nome"))
                repo.definir_parafrase(c["id"], texto)
                ok += 1
            except IAError as exc:
                falhas += 1
                erro = erro or str(exc)
        if ok:
            flash(f"{ok} paráfrase(s) gerada(s) via '{provedor.nome}'.", "ok")
        if limitado:
            flash(f"Limite diário atingido ({precos.moeda} {precos.limite_diario:.2f}) "
                  "— geração interrompida.", "aviso")
        if falhas:
            flash(f"{falhas} falharam. Primeiro erro: {erro}", "erro" if not ok else "aviso")
        if not ok and not falhas and not limitado:
            flash("Nada a parafrasear: todos os aprovados já têm texto.", "aviso")
        return redirect(url_for("informativo", empresa_id=alvo_emp))

    def _email_html_do_informativo(principal):
        """Monta o HTML do e-mail final do informativo para a empresa-alvo."""
        from ..informativo_email import montar_email_html, montar_grupos
        from ..omniroute import CaptacaoRepository

        somente = not _is_plataforma(principal)
        empresa = _empresa_do_informativo(principal)
        alvo_emp = empresa.id if empresa else principal.empresa_id
        aprovadas = CaptacaoRepository(_db()).listar_recentes(
            200, status="aprovada", empresa_id=alvo_emp,
            somente_empresa=somente or empresa is not None,
        )
        template = logo = None
        if empresa and empresa.tem_template:
            template = EmpresaRepository(_db()).obter_template(empresa.id)
        if empresa and empresa.tem_logo:
            logo = EmpresaRepository(_db()).obter_logo(empresa.id)
        html = montar_email_html(empresa, montar_grupos(aprovadas),
                                 template=template, logo=logo)
        assunto = (empresa.assunto_email if empresa else "Informativo") or "Informativo"
        return empresa, html, assunto

    @app.route("/informativo/email")
    @login_obrigatorio
    def informativo_email():
        _, html, _ = _email_html_do_informativo(_principal())
        return Response(html, mimetype="text/html")

    @app.route("/informativo/email/baixar")
    @login_obrigatorio
    def informativo_email_baixar():
        empresa, html, _ = _email_html_do_informativo(_principal())
        base = (empresa.nome if empresa else "informativo").lower()
        base = "".join(ch if ch.isalnum() else "-" for ch in base).strip("-") or "informativo"
        nome = f"informativo-{base}.html"
        return Response(html, mimetype="text/html", headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
        })

    def _email_html_de_item(principal, cid: int):
        """Monta o e-mail de **um** comunicado (padrão unitário)."""
        from ..informativo_email import montar_email_html, montar_grupos
        from ..omniroute import CaptacaoRepository

        cap = CaptacaoRepository(_db()).get(cid)
        if cap is None:
            abort(404)
        if not _is_plataforma(principal) and cap.get("empresa_id") != principal.empresa_id:
            abort(403)
        empresa = None
        if cap.get("empresa_id"):
            empresa = EmpresaRepository(_db()).get(cap["empresa_id"])
        template = logo = None
        if empresa and empresa.tem_template:
            template = EmpresaRepository(_db()).obter_template(empresa.id)
        if empresa and empresa.tem_logo:
            logo = EmpresaRepository(_db()).obter_logo(empresa.id)
        html = montar_email_html(empresa, montar_grupos([cap]),
                                 template=template, logo=logo)
        return empresa, cap, html

    @app.route("/informativo/email/<int:cid>")
    @login_obrigatorio
    def informativo_email_item(cid: int):
        _, _, html = _email_html_de_item(_principal(), cid)
        return Response(html, mimetype="text/html")

    @app.route("/informativo/email/<int:cid>/baixar")
    @login_obrigatorio
    def informativo_email_item_baixar(cid: int):
        _, _, html = _email_html_de_item(_principal(), cid)
        return Response(html, mimetype="text/html", headers={
            "Content-Disposition": f'attachment; filename="comunicado-{cid}.html"',
        })

    @app.route("/informativo/<int:cid>/disparar", methods=["POST"])
    @perfil_obrigatorio("Administrador", "Editor")
    def informativo_disparar(cid: int):
        """Marca/desmarca um comunicado como disparado (para os indicadores)."""
        from ..omniroute import CaptacaoRepository

        repo = CaptacaoRepository(_db())
        cap = repo.get(cid)
        if cap is None:
            abort(404)
        principal = _principal()
        if not _is_plataforma(principal) and cap.get("empresa_id") != principal.empresa_id:
            abort(403)
        marcar = request.form.get("desmarcar") != "1"
        repo.definir_disparado(cid, marcar)
        flash("Comunicado marcado como disparado." if marcar
              else "Marcação de disparo removida.", "ok")
        return redirect(request.referrer or url_for("informativo",
                        empresa_id=cap.get("empresa_id")))

    # -- Empresas (clientes) — gestão global (plataforma) -------------------
    @app.route("/empresas")
    @plataforma_obrigatoria
    def empresas():
        repo = EmpresaRepository(_db())
        return render_template("empresas.html", empresas=repo.listar())

    @app.route("/empresas/adicionar", methods=["POST"])
    @plataforma_obrigatoria
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
    @perfil_obrigatorio("Administrador")
    def empresa_editar(empresa_id: int):
        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        principal = _principal()
        # Plataforma edita qualquer empresa; Admin de empresa só a própria.
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        if request.method == "POST":
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
                    fonte_modelo=request.form.get("fonte_modelo") or None,
                    ativa=request.form.get("ativa", "1") == "1",
                )
                flash("Empresa atualizada.", "ok")
                destino = "empresas" if _is_plataforma(principal) else "dashboard"
                return redirect(url_for(destino))
            except ValueError as exc:
                flash(str(exc), "erro")
        from ..empresas import (
            LOGO_ALTURA_BARRA, LOGO_LARGURA_MAX, MODELOS_FONTE,
        )
        return render_template(
            "empresa_editar.html", empresa=empresa, presets=PRESETS,
            is_plataforma=_is_plataforma(principal),
            modelos_fonte=MODELOS_FONTE,
            logo_altura=LOGO_ALTURA_BARRA,
            logo_largura_max=LOGO_LARGURA_MAX,
        )

    @app.route("/empresas/<int:empresa_id>/template", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresa_template_upload(empresa_id: int):
        from ..empresas import TEMPLATE_MAX_BYTES

        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        principal = _principal()
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        arquivo = request.files.get("template")
        if not arquivo or not arquivo.filename:
            flash("Selecione um arquivo de template.", "erro")
            return redirect(url_for("empresa_editar", empresa_id=empresa_id))
        dados = arquivo.read()
        if len(dados) > TEMPLATE_MAX_BYTES:
            flash("O template excede o limite de 2 MB.", "erro")
            return redirect(url_for("empresa_editar", empresa_id=empresa_id))
        try:
            repo.salvar_template(
                empresa_id, arquivo.filename,
                arquivo.mimetype or "application/octet-stream", dados,
            )
            flash("Template do informativo enviado.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("empresa_editar", empresa_id=empresa_id))

    @app.route("/empresas/<int:empresa_id>/template/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresa_template_remover(empresa_id: int):
        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        principal = _principal()
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        repo.remover_template(empresa_id)
        flash("Template removido.", "ok")
        return redirect(url_for("empresa_editar", empresa_id=empresa_id))

    @app.route("/empresas/<int:empresa_id>/template/arquivo")
    @login_obrigatorio
    def empresa_template_arquivo(empresa_id: int):
        principal = _principal()
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        resultado = EmpresaRepository(_db()).obter_template(empresa_id)
        if resultado is None:
            abort(404)
        nome, mime, dados = resultado
        from flask import Response

        return Response(dados, mimetype=mime, headers={
            "Content-Disposition": f'inline; filename="{nome}"',
        })

    @app.route("/empresas/<int:empresa_id>/logo", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresa_logo_upload(empresa_id: int):
        from ..empresas import LOGO_MAX_BYTES

        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        principal = _principal()
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        arquivo = request.files.get("logo")
        if not arquivo or not arquivo.filename:
            flash("Selecione um arquivo de logo.", "erro")
            return redirect(url_for("empresa_editar", empresa_id=empresa_id))
        if not (arquivo.mimetype or "").startswith("image/"):
            flash("O logo deve ser uma imagem (PNG, JPG, SVG ou WEBP).", "erro")
            return redirect(url_for("empresa_editar", empresa_id=empresa_id))
        dados = arquivo.read()
        if len(dados) > LOGO_MAX_BYTES:
            flash("O logo excede o limite de 512 KB.", "erro")
            return redirect(url_for("empresa_editar", empresa_id=empresa_id))
        try:
            repo.salvar_logo(empresa_id, arquivo.filename,
                             arquivo.mimetype or "image/png", dados)
            flash("Logo enviado.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("empresa_editar", empresa_id=empresa_id))

    @app.route("/empresas/<int:empresa_id>/logo/remover", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def empresa_logo_remover(empresa_id: int):
        repo = EmpresaRepository(_db())
        if repo.get(empresa_id) is None:
            abort(404)
        principal = _principal()
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        repo.remover_logo(empresa_id)
        flash("Logo removido.", "ok")
        return redirect(url_for("empresa_editar", empresa_id=empresa_id))

    @app.route("/empresas/<int:empresa_id>/logo/arquivo")
    @login_obrigatorio
    def empresa_logo_arquivo(empresa_id: int):
        principal = _principal()
        if not (_is_plataforma(principal) or principal.empresa_id == empresa_id):
            abort(403)
        resultado = EmpresaRepository(_db()).obter_logo(empresa_id)
        if resultado is None:
            abort(404)
        nome, mime, dados = resultado
        return Response(dados, mimetype=mime, headers={
            "Content-Disposition": f'inline; filename="{nome}"',
        })

    @app.route("/empresas/<int:empresa_id>/alternar", methods=["POST"])
    @plataforma_obrigatoria
    def empresas_alternar(empresa_id: int):
        EmpresaRepository(_db()).alternar_ativa(empresa_id)
        return redirect(request.referrer or url_for("empresas"))

    @app.route("/empresas/<int:empresa_id>/remover", methods=["POST"])
    @plataforma_obrigatoria
    def empresas_remover(empresa_id: int):
        repo = EmpresaRepository(_db())
        empresa = repo.get(empresa_id)
        if empresa is None:
            abort(404)
        repo.remover(empresa_id)
        flash(f"Empresa '{empresa.nome}' removida.", "ok")
        return redirect(url_for("empresas"))

    # -- Usuários (gestão de acesso) — plataforma vê todos; Admin de empresa
    #    vê e gere só os da própria empresa.
    def _pode_gerir_usuario(principal, conta) -> bool:
        if _is_plataforma(principal):
            return True
        return conta is not None and conta.empresa_id == principal.empresa_id

    @app.route("/usuarios")
    @perfil_obrigatorio("Administrador")
    def usuarios():
        principal = _principal()
        repo = UsuarioRepository(_db())
        if _is_plataforma(principal):
            contas = repo.listar()
            empresas = EmpresaRepository(_db()).listar()
        else:
            contas = repo.listar(empresa_id=principal.empresa_id, apenas_empresa=True)
            empresas = []
        return render_template(
            "usuarios.html", contas=contas, empresas=empresas,
            is_plataforma=_is_plataforma(principal),
        )

    @app.route("/usuarios/criar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_criar():
        principal = _principal()
        repo = UsuarioRepository(_db())
        username = request.form.get("username", "")
        senha = request.form.get("senha", "")
        nome = request.form.get("nome") or None
        perfil = request.form.get("perfil", "Editor")
        if _is_plataforma(principal):
            emp = request.form.get("empresa_id") or None
            empresa_id = int(emp) if emp else None  # plataforma pode criar global
        else:
            empresa_id = principal.empresa_id  # Admin de empresa: sempre a própria
        if len(senha) < 8:
            flash("A senha deve ter ao menos 8 caracteres.", "erro")
            return redirect(url_for("usuarios"))
        try:
            conta = repo.criar(username, senha, perfil, nome=nome, empresa_id=empresa_id)
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
        if not _pode_gerir_usuario(principal, conta):
            abort(403)
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
        conta = repo.get(username)
        if conta is None:
            abort(404)
        if not _pode_gerir_usuario(_principal(), conta):
            abort(403)
        if len(nova) < 8:
            flash("A nova senha deve ter ao menos 8 caracteres.", "erro")
            return redirect(url_for("usuarios"))
        repo.redefinir_senha(username, nova)
        flash(f"Senha de '{username}' redefinida.", "ok")
        return redirect(url_for("usuarios"))

    @app.route("/usuarios/personificar", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_personificar():
        repo = UsuarioRepository(_db())
        alvo = (request.form.get("username") or "").strip().lower()
        conta = repo.get(alvo)
        if conta is None:
            abort(404)
        principal = _principal()
        if not _pode_gerir_usuario(principal, conta):
            abort(403)
        if principal and alvo == principal.username:
            flash("Você já está no seu próprio acesso.", "aviso")
            return redirect(url_for("usuarios"))
        # Guarda o admin original (mesmo ao trocar entre personificações).
        session["impersonador"] = session.get("impersonador") or session["username"]
        session["username"] = conta.username
        session["nome"] = conta.nome or conta.username
        flash(f"Você agora vê o sistema como '{conta.username}' ({conta.perfil}).", "ok")
        return redirect(url_for("dashboard"))

    @app.route("/usuarios/voltar", methods=["POST"])
    @login_obrigatorio
    def usuarios_voltar():
        admin_user = session.pop("impersonador", None)
        if not admin_user:
            return redirect(url_for("dashboard"))
        conta = UsuarioRepository(_db()).get(admin_user)
        if conta is None:
            session.clear()
            return redirect(url_for("login"))
        session["username"] = conta.username
        session["nome"] = conta.nome or conta.username
        flash("Você voltou ao seu acesso.", "ok")
        return redirect(url_for("usuarios"))

    @app.route("/usuarios/perfil", methods=["POST"])
    @perfil_obrigatorio("Administrador")
    def usuarios_perfil():
        repo = UsuarioRepository(_db())
        username = (request.form.get("username") or "").strip().lower()
        perfil = request.form.get("perfil", "Editor")
        conta = repo.get(username)
        if conta is None:
            abort(404)
        if not _pode_gerir_usuario(_principal(), conta):
            abort(403)
        try:
            repo.definir_perfil(username, perfil)
            flash(f"Perfil de '{username}' atualizado para {perfil}.", "ok")
        except ValueError as exc:
            flash(str(exc), "erro")
        return redirect(url_for("usuarios"))

    # -- Configurações: hub que reúne os módulos administrativos -------------
    @app.route("/configuracoes")
    @login_obrigatorio
    def configuracoes():
        principal = _principal()
        return render_template(
            "configuracoes.html",
            is_plataforma=_is_plataforma(principal),
            minha_empresa=principal.empresa_id,
        )

    # -- Auditoria: histórico de uso e custo de IA --------------------------
    @app.route("/auditoria")
    @perfil_obrigatorio("Administrador", "Editor")
    def auditoria():
        from ..uso import Precos, UsoRepository

        principal = _principal()
        somente = not _is_plataforma(principal)
        emp = principal.empresa_id
        uso_repo = UsoRepository(_db())
        precos = Precos(SettingsRepository(_db()))
        return render_template(
            "auditoria.html",
            historico=uso_repo.historico(30, empresa_id=emp, somente_empresa=somente),
            por_operacao=uso_repo.por_operacao(30, empresa_id=emp, somente_empresa=somente),
            resumo=uso_repo.resumo_do_dia(precos, empresa_id=emp, somente_empresa=somente),
            precos=precos,
        )

    # -- Placeholders navegáveis (próximas iterações) -----------------------
    _pagina_em_construcao(app, "newsletter_nova", "/newsletter/new", "Criar Newsletter")
    _pagina_em_construcao(app, "newsletter_preparo", "/newsletter/prepare", "Preparo do Texto")
    _pagina_em_construcao(app, "layout", "/layout", "Editor de Layout")

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
