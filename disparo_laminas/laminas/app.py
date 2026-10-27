"""Tela do Disparo de Lâminas (tkinter).

Abas:

- **Disparo** — 1) campanha e lâmina, 2) lista de envio (duplicados
  apontados, escolha de quem recebe e de quem leva cópia), 3) disparo;
- **Mensagem** — assunto e textos da campanha selecionada;
- **Enviados** — histórico com busca, exportação e importação;
- **Configurações** — limite diário, intervalo, cópia, Outlook etc.
"""

from __future__ import annotations

import os
import queue
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__
from . import config as cfgmod
from .base import (CAMPOS_BASE, DUPLICADO, ENVIADO, INVALIDO, JA_ENVIADO, PENDENTE, Cabecalho,
                   Contato, analisar, email_valido, ler_base, letra_coluna, listar_abas,
                   registros)
from .campanhas import (CAMPANHA_GERAL, lamina_do_envio, listar_anexos, listar_campanhas,
                        listar_laminas, pasta_apresentacoes, sugerir_anexo)
from .disparo import Disparo
from .envio import criar_enviador, descrever_erro, manter_pc_acordado
from .historico import Historico
from .mensagem import CAMPOS_AJUDA, montar

try:
    from PIL import Image, ImageTk
except ImportError:  # a pré-visualização da lâmina é opcional
    Image = ImageTk = None

PASTA_DADOS = cfgmod.PASTA_PROGRAMA / "dados"
ARQUIVO_HISTORICO = PASTA_DADOS / "historico_envios.db"
PASTA_SIMULACAO = PASTA_DADOS / "simulacao"

MARCADO, DESMARCADO = "☑", "☐"
FILTROS = {
    "Todos": lambda c: True,
    "Marcados para envio": lambda c: c.enviar,
    "Com cópia (CC)": lambda c: c.cc,
    "Pendentes": lambda c: c.situacao == PENDENTE,
    "Duplicados na base": lambda c: c.situacao == DUPLICADO,
    "Já enviados": lambda c: c.situacao == JA_ENVIADO,
    "Inválidos": lambda c: c.situacao == INVALIDO,
    "Enviados agora": lambda c: c.situacao == ENVIADO,
}
NENHUMA = "(nenhuma)"
ROTULO_CAMPO = {"email": "E-mail", "nome": "Nome", "empresa": "Empresa", "copia": "Cópia (S/N)"}
SEM_ANEXO = "(sem anexo)"
LIMITE_ANEXO_MB = 15
ROTULO_SITUACAO = {
    PENDENTE: "Pendente", DUPLICADO: "Duplicado", JA_ENVIADO: "Já enviado",
    INVALIDO: "Inválido", ENVIADO: "Enviado",
}


def _abrir(caminho: Path) -> None:
    if sys.platform == "win32":
        os.startfile(caminho)  # noqa: S606 - abre pasta/arquivo no Explorer
    else:
        import webbrowser
        webbrowser.open(Path(caminho).resolve().as_uri())


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Disparo de Lâminas — versão {__version__}")
        self.geometry("1180x820")
        self.minsize(980, 680)

        self.cfg = cfgmod.carregar()
        self.historico = Historico(ARQUIVO_HISTORICO)
        self.contatos: list[Contato] = []
        self.laminas_disponiveis: list[Path] = []
        self.disparo: Disparo | None = None
        self.eventos: queue.Queue = queue.Queue()
        self.proximo_envio: float | None = None
        self.proximo_contato: Contato | None = None
        self._preview = None

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=8, pady=8)
        self.aba_disparo = ttk.Frame(abas, padding=8)
        self.aba_mensagem = ttk.Frame(abas, padding=8)
        self.aba_enviados = ttk.Frame(abas, padding=8)
        self.aba_config = ttk.Frame(abas, padding=8)
        abas.add(self.aba_disparo, text="  Disparo  ")
        abas.add(self.aba_mensagem, text="  Mensagem  ")
        abas.add(self.aba_enviados, text="  Enviados  ")
        abas.add(self.aba_config, text="  Configurações  ")

        self._montar_disparo()
        self._montar_mensagem()
        self._montar_enviados()
        self._montar_config()

        self._recarregar_campanhas(self.cfg.get("ultima_campanha", ""))
        if self.cfg.get("ultima_base") and Path(self.cfg["ultima_base"]).exists():
            self.var_base.set(self.cfg["ultima_base"])
            self._atualizar_abas()
        self._atualizar_enviados()
        self._atualizar_contadores()

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self._log(f"Disparo de Lâminas versão {__version__} iniciado.")
        self.after(300, self._processar_eventos)
        self.after(1000, self._relogio)

    # ==================================================================
    # Aba Disparo
    # ==================================================================
    def _montar_disparo(self):
        aba = self.aba_disparo
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(1, weight=1)

        # -- 1. campanha e lâmina ------------------------------------------
        f1 = ttk.LabelFrame(aba, text=" 1. Do que se trata a campanha? ", padding=8)
        f1.grid(row=0, column=0, sticky="ew")
        f1.columnconfigure(1, weight=1)

        ttk.Label(f1, text="Campanha:").grid(row=0, column=0, sticky="w")
        self.var_campanha = tk.StringVar()
        self.cb_campanha = ttk.Combobox(f1, textvariable=self.var_campanha, state="readonly", width=30)
        self.cb_campanha.grid(row=0, column=1, sticky="w", padx=4)
        self.cb_campanha.bind("<<ComboboxSelected>>", lambda e: self._ao_trocar_campanha())
        botoes = ttk.Frame(f1)
        botoes.grid(row=0, column=2, sticky="e")
        ttk.Button(botoes, text="Atualizar pastas",
                   command=lambda: self._recarregar_campanhas(self.var_campanha.get())).pack(side="left", padx=2)
        ttk.Button(botoes, text="Abrir pasta das lâminas", command=self._abrir_pasta_laminas).pack(side="left", padx=2)

        ttk.Label(f1, text="Lâmina(s):").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        lista = ttk.Frame(f1)
        lista.grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        lista.columnconfigure(0, weight=1)
        self.lst_laminas = tk.Listbox(lista, height=4, selectmode="extended", exportselection=False)
        self.lst_laminas.grid(row=0, column=0, sticky="ew")
        self.lst_laminas.bind("<<ListboxSelect>>", lambda e: self._ao_trocar_lamina())
        sb = ttk.Scrollbar(lista, orient="vertical", command=self.lst_laminas.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.lst_laminas.configure(yscrollcommand=sb.set)

        opcoes = ttk.Frame(f1)
        opcoes.grid(row=2, column=1, sticky="w", padx=4)
        self.var_alternar = tk.BooleanVar(value=bool(self.cfg.get("alternar_laminas")))
        ttk.Checkbutton(opcoes, text="Mesclar: alternar entre as lâminas selecionadas a cada envio",
                        variable=self.var_alternar, command=self._ao_trocar_lamina).pack(side="left")
        ttk.Button(opcoes, text="Usar outra imagem...", command=self._escolher_imagem).pack(side="left", padx=8)

        self.lbl_lamina = ttk.Label(f1, text="", foreground="#555")
        self.lbl_lamina.grid(row=3, column=1, sticky="w", padx=4)
        self.lbl_preview = ttk.Label(f1)
        self.lbl_preview.grid(row=1, column=2, rowspan=3, sticky="e", padx=(8, 0))

        # Apresentação anexada: segue a campanha (institucional para
        # Corporativo, eventos para Eventos...), mas pode ser trocada.
        ttk.Label(f1, text="Apresentação\n(anexo):").grid(row=4, column=0, sticky="w", pady=(6, 0))
        linha_anexo = ttk.Frame(f1)
        linha_anexo.grid(row=4, column=1, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
        self.var_anexo = tk.StringVar(value=SEM_ANEXO)
        self.cb_anexo = ttk.Combobox(linha_anexo, textvariable=self.var_anexo, state="readonly", width=48)
        self.cb_anexo.pack(side="left")
        self.cb_anexo.bind("<<ComboboxSelected>>", lambda e: self._ao_trocar_anexo(salvar=True))
        ttk.Button(linha_anexo, text="Abrir pasta das apresentações",
                   command=self._abrir_pasta_anexos).pack(side="left", padx=8)
        self.lbl_anexo = ttk.Label(linha_anexo, text="", foreground="#555")
        self.lbl_anexo.pack(side="left")
        self.anexos_disponiveis: list[Path] = []

        # -- 2. lista de envio ---------------------------------------------
        f2 = ttk.LabelFrame(aba, text=" 2. Lista de envio ", padding=8)
        f2.grid(row=1, column=0, sticky="nsew", pady=8)
        f2.columnconfigure(0, weight=1)
        f2.rowconfigure(3, weight=1)

        linha = ttk.Frame(f2)
        linha.grid(row=0, column=0, sticky="ew")
        linha.columnconfigure(1, weight=1)
        ttk.Label(linha, text="Planilha:").grid(row=0, column=0)
        self.var_base = tk.StringVar()
        ttk.Entry(linha, textvariable=self.var_base).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(linha, text="Escolher...", command=self._escolher_base).grid(row=0, column=2)
        ttk.Label(linha, text="Aba:").grid(row=0, column=3, padx=(8, 0))
        self.var_aba = tk.StringVar()
        self.cb_aba = ttk.Combobox(linha, textvariable=self.var_aba, state="readonly", width=18)
        self.cb_aba.grid(row=0, column=4, padx=4)
        ttk.Button(linha, text="Carregar / Recarregar", command=self._carregar_base).grid(row=0, column=5)
        self.cb_aba.bind("<<ComboboxSelected>>", lambda e: self._carregar_base())

        # Qual coluna da planilha é cada campo (detectado pelo título, em
        # qualquer ordem; dá para trocar manualmente).
        mapa = ttk.Frame(f2)
        mapa.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(mapa, text="Colunas:").pack(side="left")
        self.cb_colunas: dict[str, ttk.Combobox] = {}
        for campo in CAMPOS_BASE:
            ttk.Label(mapa, text=f"  {ROTULO_CAMPO[campo]}").pack(side="left")
            cb = ttk.Combobox(mapa, state="readonly", width=22, values=[NENHUMA])
            cb.set(NENHUMA)
            cb.pack(side="left", padx=2)
            cb.bind("<<ComboboxSelected>>", lambda e, c=campo: self._trocar_coluna(c))
            self.cb_colunas[campo] = cb
        self.cabecalho: Cabecalho | None = None

        linha2 = ttk.Frame(f2)
        linha2.grid(row=2, column=0, sticky="ew", pady=(6, 4))
        self.lbl_resumo = ttk.Label(linha2, text="Nenhuma planilha carregada.")
        self.lbl_resumo.pack(side="left")
        self.var_filtro = tk.StringVar(value="Todos")
        cb_filtro = ttk.Combobox(linha2, textvariable=self.var_filtro, values=list(FILTROS),
                                 state="readonly", width=20)
        cb_filtro.pack(side="right")
        cb_filtro.bind("<<ComboboxSelected>>", lambda e: self._preencher_tabela())
        ttk.Label(linha2, text="Mostrar:").pack(side="right", padx=4)

        tabela = ttk.Frame(f2)
        tabela.grid(row=3, column=0, sticky="nsew")
        tabela.columnconfigure(0, weight=1)
        tabela.rowconfigure(0, weight=1)
        colunas = ("enviar", "cc", "linha", "empresa", "nome", "email", "situacao")
        self.tv = ttk.Treeview(tabela, columns=colunas, show="headings", selectmode="extended")
        for col, titulo, larg, ancora in (
            ("enviar", "Enviar", 60, "center"), ("cc", "CC", 45, "center"),
            ("linha", "Linha", 55, "e"), ("empresa", "Empresa", 210, "w"),
            ("nome", "Nome", 210, "w"), ("email", "E-mail", 260, "w"),
            ("situacao", "Situação", 260, "w"),
        ):
            self.tv.heading(col, text=titulo)
            self.tv.column(col, width=larg, anchor=ancora, stretch=col in ("empresa", "nome", "email", "situacao"))
        self.tv.grid(row=0, column=0, sticky="nsew")
        sb2 = ttk.Scrollbar(tabela, orient="vertical", command=self.tv.yview)
        sb2.grid(row=0, column=1, sticky="ns")
        self.tv.configure(yscrollcommand=sb2.set)
        self.tv.tag_configure(DUPLICADO, background="#fbd5d5")
        self.tv.tag_configure(JA_ENVIADO, background="#fff1c7")
        self.tv.tag_configure(INVALIDO, foreground="#888888")
        self.tv.tag_configure(ENVIADO, background="#d9f2d9")
        self.tv.tag_configure("enviando", background="#d6e6ff")
        self.tv.bind("<Button-1>", self._clique_tabela)

        acoes = ttk.Frame(f2)
        acoes.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(acoes, text="Enviar:").pack(side="left")
        ttk.Button(acoes, text="Marcar todos pendentes", command=self._marcar_todos).pack(side="left", padx=2)
        ttk.Button(acoes, text="Marcar só os de hoje", command=self._marcar_proximos).pack(side="left", padx=2)
        ttk.Button(acoes, text="Desmarcar todos", command=self._desmarcar_todos).pack(side="left", padx=2)
        ttk.Separator(acoes, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(acoes, text="Cópia:").pack(side="left")
        ttk.Button(acoes, text="CC nas linhas selecionadas", command=lambda: self._cc_selecionadas(True)).pack(side="left", padx=2)
        ttk.Button(acoes, text="Tirar CC das selecionadas", command=lambda: self._cc_selecionadas(False)).pack(side="left", padx=2)
        ttk.Button(acoes, text="Limpar todas as cópias", command=self._cc_limpar).pack(side="left", padx=2)
        ttk.Label(f2, text="Dica: clique na coluna Enviar ou CC para marcar/desmarcar. "
                           "Use Ctrl/Shift para selecionar várias linhas.",
                  foreground="#666").grid(row=5, column=0, sticky="w", pady=(4, 0))

        # -- 3. disparo -----------------------------------------------------
        f3 = ttk.LabelFrame(aba, text=" 3. Disparo ", padding=8)
        f3.grid(row=2, column=0, sticky="ew")
        f3.columnconfigure(1, weight=1)
        ttk.Label(f3, text="Cópia (CC) para:").grid(row=0, column=0, sticky="w")
        self.var_cc = tk.StringVar(value=self.cfg.get("email_copia", ""))
        ttk.Entry(f3, textvariable=self.var_cc, width=40).grid(row=0, column=1, sticky="w", padx=4)
        self.lbl_contadores = ttk.Label(f3, text="")
        self.lbl_contadores.grid(row=1, column=0, columnspan=3, sticky="w", pady=4)

        botoes = ttk.Frame(f3)
        botoes.grid(row=0, column=2, sticky="e")
        ttk.Button(botoes, text="Pré-visualizar", command=self._previsualizar).pack(side="left", padx=2)
        ttk.Button(botoes, text="Enviar teste...", command=self._enviar_teste).pack(side="left", padx=2)
        self.bt_iniciar = ttk.Button(botoes, text="▶  Iniciar disparo", command=self._iniciar)
        self.bt_iniciar.pack(side="left", padx=2)
        self.bt_parar = ttk.Button(botoes, text="■  Parar", command=self._parar, state="disabled")
        self.bt_parar.pack(side="left", padx=2)

        self.lbl_status = ttk.Label(f3, text="Parado.", font=("Segoe UI", 11, "bold"))
        self.lbl_status.grid(row=2, column=0, columnspan=3, sticky="w")
        self.txt_log = ScrolledText(f3, height=5, state="disabled", font=("Consolas", 9))
        self.txt_log.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    # -- campanha / lâminas -------------------------------------------------
    def _recarregar_campanhas(self, preferida: str = ""):
        campanhas = listar_campanhas(self.cfg.get("pasta_laminas", ""))
        self.cb_campanha["values"] = campanhas
        if not campanhas:
            self.var_campanha.set("")
            self.lbl_lamina.configure(
                text="Pasta de lâminas não encontrada ou vazia — ajuste em Configurações "
                     "ou use 'Usar outra imagem...'.", foreground="#b00020")
        else:
            escolhida = next((c for c in campanhas if c.casefold() == (preferida or "").casefold()), None)
            self.var_campanha.set(escolhida or campanhas[0])
        self._ao_trocar_campanha()

    def _ao_trocar_campanha(self):
        campanha = self.var_campanha.get()
        self.laminas_disponiveis = listar_laminas(self.cfg.get("pasta_laminas", ""), campanha)
        self.lst_laminas.delete(0, "end")
        for p in self.laminas_disponiveis:
            data = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y")
            self.lst_laminas.insert("end", f"{p.name}   ({data})")
        if self.laminas_disponiveis:
            self.lst_laminas.selection_set(0)
        if campanha and campanha != self.cfg.get("ultima_campanha"):
            self.cfg["ultima_campanha"] = campanha
            cfgmod.salvar(self.cfg)
        self._carregar_mensagem_na_tela()
        self._ao_trocar_lamina()
        self._recarregar_anexos()

    # -- apresentação (anexo) -------------------------------------------------
    def _pasta_anexos(self) -> Path | None:
        return pasta_apresentacoes(self.cfg.get("pasta_laminas", ""), self.cfg.get("pasta_anexos", ""))

    def _recarregar_anexos(self):
        """Lista as apresentações e escolhe a da campanha: a definida na tela
        antes (lembrada por campanha) ou a que combina pelo nome do arquivo."""
        campanha = self.var_campanha.get()
        self.anexos_disponiveis = listar_anexos(self._pasta_anexos())
        nomes = [p.name for p in self.anexos_disponiveis]
        self.cb_anexo["values"] = [SEM_ANEXO] + nomes
        definido = (self.cfg.get("anexos_por_campanha") or {}).get(campanha)
        if definido is not None and (definido == "" or definido in nomes):
            escolha = definido or SEM_ANEXO
        else:
            sugerido = sugerir_anexo(self.anexos_disponiveis, campanha)
            escolha = sugerido.name if sugerido else SEM_ANEXO
        self.var_anexo.set(escolha)
        self._ao_trocar_anexo(salvar=False)

    def _anexos_escolhidos(self) -> list[Path]:
        nome = self.var_anexo.get()
        return [p for p in self.anexos_disponiveis if p.name == nome]

    def _ao_trocar_anexo(self, salvar: bool):
        campanha = self.var_campanha.get()
        if salvar and campanha:
            nome = self.var_anexo.get()
            self.cfg.setdefault("anexos_por_campanha", {})[campanha] = "" if nome == SEM_ANEXO else nome
            cfgmod.salvar(self.cfg)
        anexos = self._anexos_escolhidos()
        if anexos:
            mb = anexos[0].stat().st_size / 1024 / 1024
            aviso = "  ⚠ arquivo grande: pode ser recusado pelo servidor" if mb > LIMITE_ANEXO_MB else ""
            self.lbl_anexo.configure(text=f"{mb:.1f} MB{aviso}",
                                     foreground="#b00020" if aviso else "#555")
        elif not self.anexos_disponiveis:
            pasta = self._pasta_anexos()
            self.lbl_anexo.configure(text=f"Nenhuma apresentação em {pasta}" if pasta else "",
                                     foreground="#b00020")
        else:
            self.lbl_anexo.configure(text="Sem anexo para esta campanha.", foreground="#555")

    def _abrir_pasta_anexos(self):
        pasta = self._pasta_anexos()
        if pasta and pasta.is_dir():
            _abrir(pasta)
        else:
            messagebox.showwarning("Pasta não encontrada",
                                   f"A pasta das apresentações não existe:\n{pasta}\n\n"
                                   "Crie a pasta APRESENTAÇÃO dentro da pasta das lâminas "
                                   "ou ajuste em Configurações.")

    def _laminas_escolhidas(self) -> list[Path]:
        return [self.laminas_disponiveis[i] for i in self.lst_laminas.curselection()]

    def _ao_trocar_lamina(self):
        escolhidas = self._laminas_escolhidas()
        if not escolhidas:
            if self.laminas_disponiveis:
                self.lbl_lamina.configure(text="Selecione a lâmina a enviar.", foreground="#b00020")
            self._mostrar_preview(None)
            return
        if len(escolhidas) > 1 and self.var_alternar.get():
            texto = f"{len(escolhidas)} lâminas mescladas em rodízio: " + ", ".join(p.name for p in escolhidas)
        elif len(escolhidas) > 1:
            texto = (f"Será usada só a primeira ({escolhidas[0].name}). "
                     "Marque 'Mesclar' para alternar entre as selecionadas.")
        else:
            texto = f"Lâmina: {escolhidas[0]}"
        self.lbl_lamina.configure(text=texto, foreground="#555")
        self._mostrar_preview(escolhidas[0])
        if bool(self.var_alternar.get()) != bool(self.cfg.get("alternar_laminas")):
            self.cfg["alternar_laminas"] = bool(self.var_alternar.get())
            cfgmod.salvar(self.cfg)

    def _mostrar_preview(self, caminho: Path | None):
        if caminho is None or Image is None:
            self.lbl_preview.configure(image="", text="" if Image else "(instale Pillow\npara ver a prévia)")
            self._preview = None
            return
        try:
            img = Image.open(caminho)
            img.thumbnail((200, 200))
            self._preview = ImageTk.PhotoImage(img)
            self.lbl_preview.configure(image=self._preview, text="")
        except OSError:
            self.lbl_preview.configure(image="", text="(prévia indisponível)")
            self._preview = None

    def _escolher_imagem(self):
        arquivos = filedialog.askopenfilenames(
            title="Escolha a(s) lâmina(s)",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.gif"), ("Todos", "*.*")],
            initialdir=self.cfg.get("pasta_laminas") or None,
        )
        if not arquivos:
            return
        self.lst_laminas.selection_clear(0, "end")
        for a in arquivos:
            p = Path(a)
            if p not in self.laminas_disponiveis:
                self.laminas_disponiveis.append(p)
                self.lst_laminas.insert("end", f"{p.name}   (avulsa)")
            self.lst_laminas.selection_set(self.laminas_disponiveis.index(p))
        if not self.var_campanha.get():
            self.var_campanha.set(CAMPANHA_GERAL)
            self._carregar_mensagem_na_tela()
        self._ao_trocar_lamina()

    def _abrir_pasta_laminas(self):
        pasta = Path(self.cfg.get("pasta_laminas", ""))
        if pasta.is_dir():
            _abrir(pasta)
        else:
            messagebox.showwarning("Pasta não encontrada",
                                   f"A pasta das lâminas não existe:\n{pasta}\n\nAjuste em Configurações.")

    # -- base ----------------------------------------------------------------
    def _escolher_base(self):
        arquivo = filedialog.askopenfilename(
            title="Planilha com a lista de envio",
            filetypes=[("Planilhas", "*.xlsx *.xlsm *.csv"), ("Todos", "*.*")],
        )
        if arquivo:
            self.var_base.set(arquivo)
            self._atualizar_abas()
            self._carregar_base()

    def _atualizar_abas(self):
        caminho = self.var_base.get()
        try:
            abas = listar_abas(caminho)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Planilha", f"Não foi possível abrir a planilha:\n{exc}")
            return
        self.cb_aba["values"] = abas
        preferida = self.cfg.get("aba_padrao", "")
        atual = self.var_aba.get()
        if atual in abas:
            return
        self.var_aba.set(preferida if preferida in abas else (abas[0] if abas else ""))

    def _carregar_base(self):
        if self._em_disparo():
            return
        caminho = self.var_base.get().strip()
        if not caminho or not Path(caminho).exists():
            messagebox.showwarning("Lista de envio", "Escolha a planilha com a lista de envio.")
            return
        if not self.cb_aba["values"]:
            self._atualizar_abas()
        aba = self.var_aba.get() or None
        try:
            regs, cab = ler_base(caminho, aba)
            manual = self._mapa_salvo(cab)
            if manual:
                regs, cab = ler_base(caminho, aba, manual)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Lista de envio", f"Erro ao ler a planilha:\n{exc}")
            return
        self.cabecalho = cab
        self._mostrar_colunas(cab)

        # Recarregar mantém as marcações de cópia feitas na tela.
        cc_antes = {c.email_norm for c in self.contatos if c.cc}
        self.contatos, resumo = analisar(regs, self.historico.ja_enviados())
        for c in self.contatos:
            if c.email_norm in cc_antes and c.situacao == PENDENTE:
                c.cc = True

        self.cfg["ultima_base"] = caminho
        cfgmod.salvar(self.cfg)
        self._preencher_tabela()
        self.lbl_resumo.configure(text=(
            f"{resumo.total} contatos · {resumo.pendentes} pendentes · "
            f"{len(resumo.duplicados)} duplicados · {resumo.ja_enviados} já enviados · "
            f"{resumo.invalidos} inválidos"))
        self._atualizar_contadores()
        self._log(f"Lista carregada: {Path(caminho).name} [{self.var_aba.get() or 'CSV'}] — "
                  f"{resumo.pendentes} pendentes. Colunas: "
                  + " · ".join(f"{ROTULO_CAMPO[c]} = {cab.descricao(c)}" for c in ("email", "nome", "empresa")))

        faltando = [ROTULO_CAMPO[c] for c in ("nome", "empresa") if c not in cab.colunas]
        if faltando:
            messagebox.showwarning(
                "Colunas não encontradas",
                f"Não identifiquei a coluna de {' e '.join(faltando)} pelo título.\n\n"
                "Escolha a coluna certa nos campos 'Colunas' (logo abaixo da planilha). "
                "Sem nome e empresa o contato não pode ser enviado.")

        if resumo.duplicados:
            linhas = [f"• {email} — linhas {', '.join(map(str, ns))}"
                      for email, ns in list(resumo.duplicados.items())[:25]]
            extra = len(resumo.duplicados) - 25
            if extra > 0:
                linhas.append(f"... e mais {extra}.")
            messagebox.showwarning(
                "E-mails duplicados na base",
                f"Encontrei {len(resumo.duplicados)} e-mail(s) repetido(s) na planilha. "
                "Só a primeira ocorrência será enviada; as repetições ficam bloqueadas "
                "(em vermelho na lista).\n\n" + "\n".join(linhas))

    def _chave_mapa(self) -> str:
        return f"{Path(self.var_base.get()).name}|{self.var_aba.get()}"

    def _mapa_salvo(self, cab: Cabecalho) -> dict[str, int | None]:
        """Escolhas manuais de coluna salvas para esta planilha/aba, achadas
        pelo título (continua valendo se as colunas mudarem de lugar)."""
        salvo = (self.cfg.get("mapa_colunas") or {}).get(self._chave_mapa()) or {}
        manual: dict[str, int | None] = {}
        for campo, ref in salvo.items():
            if ref is None:
                manual[campo] = None
            elif ref in cab.titulos:
                manual[campo] = cab.titulos.index(ref)
            elif ref.startswith("#") and ref[1:].isdigit():
                manual[campo] = int(ref[1:])
        return manual

    def _mostrar_colunas(self, cab: Cabecalho):
        opcoes = [NENHUMA] + [f"{letra_coluna(j)} - {t}" if t else letra_coluna(j)
                              for j, t in enumerate(cab.titulos)]
        for campo, cb in self.cb_colunas.items():
            cb["values"] = opcoes
            cb.set(cab.descricao(campo))

    def _trocar_coluna(self, campo: str):
        if self.cabecalho is None or self._em_disparo(avisar=True):
            return
        escolha = self.cb_colunas[campo].get()
        opcoes = list(self.cb_colunas[campo]["values"])
        j = opcoes.index(escolha) - 1 if escolha in opcoes else -1
        if j < 0:
            ref = None
        else:
            titulo = self.cabecalho.titulos[j]
            ref = titulo if titulo and self.cabecalho.titulos.count(titulo) == 1 else f"#{j}"
        mapas = self.cfg.setdefault("mapa_colunas", {})
        mapas.setdefault(self._chave_mapa(), {})[campo] = ref
        cfgmod.salvar(self.cfg)
        self._carregar_base()

    def _preencher_tabela(self):
        filtro = FILTROS.get(self.var_filtro.get(), FILTROS["Todos"])
        self.tv.delete(*self.tv.get_children())
        for i, c in enumerate(self.contatos):
            if filtro(c):
                self.tv.insert("", "end", iid=str(i), values=self._valores(c), tags=(c.situacao,))

    def _valores(self, c: Contato) -> tuple:
        situacao = ROTULO_SITUACAO.get(c.situacao, c.situacao)
        if c.detalhe:
            situacao = c.detalhe if c.situacao != PENDENTE else f"{situacao} — {c.detalhe}"
        if c.forcar and c.enviar:
            situacao += " (reenvio autorizado)"
        podem_marcar = c.selecionavel
        return (MARCADO if c.enviar else (DESMARCADO if podem_marcar else "—"),
                MARCADO if c.cc else (DESMARCADO if podem_marcar else ""),
                c.linha, c.empresa, c.nome, c.email, situacao)

    def _atualizar_linha(self, indice: int, tag: str | None = None):
        iid = str(indice)
        if self.tv.exists(iid):
            c = self.contatos[indice]
            self.tv.item(iid, values=self._valores(c), tags=(tag or c.situacao,))

    def _clique_tabela(self, evento):
        if self.tv.identify_region(evento.x, evento.y) != "cell":
            return None
        coluna = self.tv.identify_column(evento.x)
        iid = self.tv.identify_row(evento.y)
        if not iid or coluna not in ("#1", "#2"):
            return None
        if self._em_disparo(avisar=True):
            return "break"
        c = self.contatos[int(iid)]
        if coluna == "#1":
            self._alternar_envio(c)
        else:
            self._alternar_cc(c)
        self._atualizar_linha(int(iid))
        self._atualizar_contadores()
        return "break"

    def _alternar_envio(self, c: Contato):
        if c.enviar:
            c.enviar = c.forcar = False
            return
        if c.situacao == JA_ENVIADO:
            if messagebox.askyesno("Já enviado",
                                   f"{c.email} já recebeu lâmina.\n{c.detalhe}.\n\n"
                                   "Deseja enviar novamente para este contato?",
                                   icon="warning"):
                c.enviar = c.forcar = True
        elif c.situacao == PENDENTE:
            c.enviar = True
        else:
            messagebox.showinfo("Não disponível", f"Este contato não pode ser enviado:\n{c.detalhe or c.situacao}")

    def _alternar_cc(self, c: Contato):
        if not c.selecionavel:
            return
        c.cc = not c.cc
        if c.cc and not self.var_cc.get().strip():
            messagebox.showinfo("Cópia", "Preencha o campo 'Cópia (CC) para' no quadro 3 (Disparo).")

    def _marcar_todos(self):
        if self._em_disparo(avisar=True):
            return
        for c in self.contatos:
            if c.situacao == PENDENTE:
                c.enviar = True
        self._preencher_tabela()
        self._atualizar_contadores()

    def _marcar_proximos(self):
        if self._em_disparo(avisar=True):
            return
        restam = self._restam_hoje()
        for c in self.contatos:
            c.enviar = c.forcar = False
        for c in self.contatos:
            if restam <= 0:
                break
            if c.situacao == PENDENTE:
                c.enviar = True
                restam -= 1
        self._preencher_tabela()
        self._atualizar_contadores()

    def _desmarcar_todos(self):
        if self._em_disparo(avisar=True):
            return
        for c in self.contatos:
            c.enviar = c.forcar = False
        self._preencher_tabela()
        self._atualizar_contadores()

    def _cc_selecionadas(self, valor: bool):
        if self._em_disparo(avisar=True):
            return
        selecionadas = self.tv.selection()
        if not selecionadas:
            messagebox.showinfo("Cópia", "Selecione na lista as linhas que devem (ou não) levar cópia.")
            return
        for iid in selecionadas:
            c = self.contatos[int(iid)]
            if c.selecionavel:
                c.cc = valor
                self._atualizar_linha(int(iid))
        if valor and not self.var_cc.get().strip():
            messagebox.showinfo("Cópia", "Preencha o campo 'Cópia (CC) para' no quadro 3 (Disparo).")
        self._atualizar_contadores()

    def _cc_limpar(self):
        if self._em_disparo(avisar=True):
            return
        for c in self.contatos:
            c.cc = False
        self._preencher_tabela()
        self._atualizar_contadores()

    # -- contadores / log ----------------------------------------------------
    def _limite(self) -> int:
        return int(self.cfg.get("limite_diario") or 80)

    def _intervalo_min(self) -> float:
        return float(self.cfg.get("intervalo_minutos") or 3)

    def _restam_hoje(self) -> int:
        return max(0, self._limite() - self.historico.enviados_no_dia())

    def _selecionados(self) -> list[Contato]:
        return [c for c in self.contatos if c.enviar]

    def _atualizar_contadores(self):
        hoje = self.historico.enviados_no_dia()
        sel = self._selecionados()
        com_cc = sum(c.cc for c in sel)
        restam = max(0, self._limite() - hoje)
        vao_hoje = min(len(sel), restam)
        texto = (f"Hoje: {hoje} de {self._limite()} enviados (restam {restam})  ·  "
                 f"Marcados: {len(sel)} (com CC: {com_cc})  ·  Intervalo: {self._intervalo_min():g} min")
        if vao_hoje and not self._em_disparo():
            fim = datetime.now() + timedelta(minutes=self._intervalo_min() * (vao_hoje - 1))
            texto += f"  ·  {vao_hoje} sairiam hoje, término previsto ~{fim:%H:%M}"
        if self.cfg.get("modo_simulacao"):
            texto += "  ·  MODO SIMULAÇÃO (nada é enviado)"
        self.lbl_contadores.configure(text=texto)

    def _log(self, texto: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"[{datetime.now():%H:%M:%S}] {texto}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    # -- pré-visualização / disparo -----------------------------------------
    def _em_disparo(self, avisar: bool = False) -> bool:
        rodando = self.disparo is not None and self.disparo.is_alive()
        if rodando and avisar:
            messagebox.showinfo("Disparo em andamento", "Pare o disparo para alterar a lista.")
        return rodando

    def _mensagem_atual(self) -> dict:
        return {
            "assunto": self.var_assunto.get(),
            "texto_inicio": self.txt_inicio.get("1.0", "end-1c"),
            "texto_fim": self.txt_fim.get("1.0", "end-1c"),
        }

    def _contato_exemplo(self, titulo: str) -> Contato | None:
        """Contato selecionado na lista (ou o 1º marcado) para montar um exemplo."""
        selecionadas = [self.contatos[int(i)] for i in self.tv.selection()]
        alvo = next(iter(selecionadas), None) or next(iter(self._selecionados()), None)
        if alvo is None:
            messagebox.showinfo(titulo, "Carregue a lista e marque (ou selecione) um contato.")
            return None
        if not alvo.nome or not alvo.empresa or not alvo.selecionavel:
            messagebox.showwarning(
                titulo,
                f"Linha {alvo.linha} ({alvo.email or 'sem e-mail'}) não pode ser usada: "
                f"{alvo.detalhe or 'faltam dados'}.\n\nSe o nome ou a empresa estão na planilha, "
                "confira os campos 'Colunas' logo abaixo da planilha.")
            return None
        return alvo

    def _email_exemplo(self, alvo: Contato, cc: str):
        return montar(alvo, self._mensagem_atual(),
                      imagem=lamina_do_envio(self._laminas_escolhidas(), 0, self.var_alternar.get()),
                      cc=cc, cco=self.cfg.get("copia_oculta", ""), anexos=self._anexos_escolhidos())

    def _previsualizar(self):
        alvo = self._contato_exemplo("Pré-visualizar")
        if alvo is None:
            return
        email = self._email_exemplo(alvo, self.var_cc.get().strip())
        try:
            criar_enviador(self.cfg, PASTA_SIMULACAO).exibir(email)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Pré-visualizar", descrever_erro(exc))

    def _enviar_teste(self):
        """Envia de verdade (lâmina, anexo e texto do contato escolhido) para um
        endereço de teste, sem cópia e sem registrar na lista de enviados."""
        alvo = self._contato_exemplo("Enviar teste")
        if alvo is None:
            return
        destino = simpledialog.askstring(
            "Enviar teste",
            f"Enviar um e-mail de TESTE montado com os dados de {alvo.nome} ({alvo.empresa}) para:",
            initialvalue=self.cfg.get("email_teste", ""), parent=self)
        if not destino:
            return
        destino = destino.strip()
        if not email_valido(destino):
            messagebox.showerror("Enviar teste", f"E-mail inválido: {destino}")
            return
        self.cfg["email_teste"] = destino
        cfgmod.salvar(self.cfg)
        email = self._email_exemplo(alvo, cc="")
        email.para, email.assunto = destino, f"[TESTE] {email.assunto}"
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            obs = criar_enviador(self.cfg, PASTA_SIMULACAO).enviar(email)
        except Exception as exc:  # noqa: BLE001
            self._log(f"✖ teste para {destino}: {descrever_erro(exc)}")
            messagebox.showerror("Enviar teste", descrever_erro(exc))
            return
        finally:
            self.configure(cursor="")
        self._log(f"✔ teste enviado para {destino}" + (f" ({obs})" if obs else ""))
        messagebox.showinfo("Enviar teste", f"Teste enviado para {destino}." + (f"\n\n{obs}" if obs else ""))

    def _validar_disparo(self) -> str | None:
        sel = self._selecionados()
        if not self.contatos:
            return "Carregue a lista de envio (quadro 2)."
        if not sel:
            return "Nenhum contato marcado para envio."
        laminas = self._laminas_escolhidas()
        if not laminas:
            return "Escolha a campanha e selecione a lâmina (quadro 1)."
        faltando = [p.name for p in laminas if not p.is_file()]
        if faltando:
            return "Lâmina não encontrada: " + ", ".join(faltando)
        if self.var_anexo.get() != SEM_ANEXO and not any(p.is_file() for p in self._anexos_escolhidos()):
            return f"Apresentação não encontrada: {self.var_anexo.get()}. Clique em 'Atualizar pastas'."
        if any(c.cc for c in sel):
            cc = self.var_cc.get().strip()
            if not all(email_valido(x.strip()) for x in cc.replace(",", ";").split(";") if x.strip()) or not cc:
                return "Há contatos marcados com cópia, mas o e-mail de 'Cópia (CC) para' está vazio ou inválido."
        if not self._mensagem_atual()["assunto"].strip():
            return "O assunto está vazio (aba Mensagem)."
        if self._restam_hoje() <= 0:
            return f"O limite de {self._limite()} envios de hoje já foi atingido."
        return None

    def _iniciar(self):
        if self._em_disparo():
            return
        erro = self._validar_disparo()
        if erro:
            messagebox.showwarning("Disparo", erro)
            return
        self._oferecer_salvar_mensagem()

        sel = self._selecionados()
        restam = self._restam_hoje()
        vao = min(len(sel), restam)
        laminas = self._laminas_escolhidas()
        alternar = self.var_alternar.get() and len(laminas) > 1
        intervalo = self._intervalo_min()
        fim = datetime.now() + timedelta(minutes=intervalo * (vao - 1))
        com_cc = sum(c.cc for c in sel[:vao])
        reenvios = sum(c.forcar for c in sel[:vao])
        modo = "SIMULAÇÃO (gera arquivos, nada é enviado)" if self.cfg.get("modo_simulacao") else "OUTLOOK — envio real"
        resumo = [
            f"Campanha: {self.var_campanha.get() or '-'}",
            "Lâmina(s): " + ", ".join(p.name for p in (laminas if alternar else laminas[:1]))
            + (" (alternando)" if alternar else ""),
            "Anexo: " + (", ".join(p.name for p in self._anexos_escolhidos()) or "nenhum"),
            f"Contatos marcados: {len(sel)}",
            f"Serão enviados agora: {vao}" + (f"  (os outros {len(sel) - vao} ficam para outro dia — limite {self._limite()}/dia)" if vao < len(sel) else ""),
            f"Com cópia para {self.var_cc.get().strip()}: {com_cc}" if com_cc else "Sem cópia (CC)",
            f"Reenvios autorizados: {reenvios}" if reenvios else "",
            f"Intervalo: {intervalo:g} min  →  término previsto ~{fim:%H:%M}",
            f"Modo: {modo}",
        ]
        if not messagebox.askyesno("Confirmar disparo", "\n".join(x for x in resumo if x) + "\n\nConfirma o disparo?"):
            return

        cfg = dict(self.cfg)
        self.disparo = Disparo(
            sel,
            historico=self.historico,
            criar_enviador=lambda: criar_enviador(cfg, PASTA_SIMULACAO),
            mensagem=self._mensagem_atual(),
            campanha=self.var_campanha.get(),
            laminas=laminas,
            alternar_laminas=alternar,
            anexos=self._anexos_escolhidos(),
            email_copia=self.var_cc.get().strip(),
            copia_oculta=self.cfg.get("copia_oculta", ""),
            limite_diario=self._limite(),
            intervalo_seg=intervalo * 60,
            eventos=self.eventos,
        )
        self.indice_por_contato = {id(c): i for i, c in enumerate(self.contatos)}
        self.total_disparo = vao
        self.feitos_disparo = 0
        self.bt_iniciar.configure(state="disabled")
        self.bt_parar.configure(state="normal")
        manter_pc_acordado(True)
        self._log(f"Disparo iniciado: {vao} e-mail(s), intervalo {intervalo:g} min.")
        self.lbl_status.configure(text="Abrindo o Outlook...")
        self.disparo.start()
        self._atualizar_contadores()

    def _parar(self):
        if self._em_disparo() and messagebox.askyesno(
                "Parar disparo", "Parar o disparo? Os contatos não enviados continuam pendentes."):
            self.disparo.parar()
            self.lbl_status.configure(text="Parando...")

    def _indice(self, contato: Contato) -> int | None:
        return getattr(self, "indice_por_contato", {}).get(id(contato))

    def _processar_eventos(self):
        try:
            while True:
                tipo, dados = self.eventos.get_nowait()
                self._tratar_evento(tipo, dados)
        except queue.Empty:
            pass
        self.after(300, self._processar_eventos)

    def _tratar_evento(self, tipo: str, dados: dict):
        c: Contato | None = dados.get("contato")
        i = self._indice(c) if c is not None else None
        if tipo == "aguardando":
            self.proximo_envio = time.monotonic() + dados["segundos"]
            self.proximo_contato = c
        elif tipo == "enviando":
            self.proximo_envio = None
            self.lbl_status.configure(text=f"Enviando para {c.nome} <{c.email}>...")
            if i is not None:
                self._atualizar_linha(i, "enviando")
        elif tipo == "enviado":
            self.feitos_disparo += 1
            c.situacao, c.enviar, c.forcar = ENVIADO, False, False
            c.detalhe = f"Enviado às {datetime.now():%H:%M:%S}" + (" com CC" if dados["email"].cc else "")
            if i is not None:
                self._atualizar_linha(i)
            self._log(f"✔ ({self.feitos_disparo}/{self.total_disparo}) {c.email}"
                      + (f"  CC: {dados['email'].cc}" if dados["email"].cc else "")
                      + (f"  [{dados['email'].imagem.name}]" if dados["email"].imagem else "")
                      + (f"  ({dados['obs']})" if dados.get("obs") else ""))
            self.lbl_status.configure(text=f"Enviado {self.feitos_disparo} de {self.total_disparo}.")
            self._atualizar_enviados()
            self._atualizar_contadores()
        elif tipo == "erro":
            c.enviar = c.forcar = False
            c.detalhe = f"Erro no envio: {dados['erro']}"
            if i is not None:
                self._atualizar_linha(i)
            self._log(f"✖ {c.email}: {dados['erro']}")
            self._atualizar_enviados()
        elif tipo == "pulado":
            c.situacao, c.enviar = JA_ENVIADO, False
            c.detalhe = dados["motivo"]
            if i is not None:
                self._atualizar_linha(i)
            self._log(f"— pulado {c.email}: {dados['motivo']}")
        elif tipo == "fim":
            self.proximo_envio = None
            manter_pc_acordado(False)
            self.bt_iniciar.configure(state="normal")
            self.bt_parar.configure(state="disabled")
            texto = f"{dados['motivo']} Enviados: {dados['enviados']}. Erros: {dados['erros']}."
            self.lbl_status.configure(text=texto)
            self._log(texto)
            self._atualizar_enviados()
            self._atualizar_contadores()
            messagebox.showinfo("Disparo", texto)

    def _relogio(self):
        if self.proximo_envio is not None:
            falta = max(0, int(self.proximo_envio - time.monotonic()))
            c = self.proximo_contato
            alvo = f" para {c.nome} <{c.email}>" if c else ""
            self.lbl_status.configure(
                text=f"Próximo envio em {falta // 60:02d}:{falta % 60:02d}{alvo}  "
                     f"({self.feitos_disparo} de {self.total_disparo} enviados)")
        self.after(1000, self._relogio)

    # ==================================================================
    # Aba Mensagem
    # ==================================================================
    def _montar_mensagem(self):
        aba = self.aba_mensagem
        aba.columnconfigure(0, weight=1)
        self.lbl_msg_campanha = ttk.Label(aba, text="", font=("Segoe UI", 11, "bold"))
        self.lbl_msg_campanha.grid(row=0, column=0, sticky="w")
        self.lbl_msg_origem = ttk.Label(aba, text="", foreground="#555")
        self.lbl_msg_origem.grid(row=1, column=0, sticky="w", pady=(0, 8))

        ttk.Label(aba, text="Assunto:").grid(row=2, column=0, sticky="w")
        self.var_assunto = tk.StringVar()
        ttk.Entry(aba, textvariable=self.var_assunto).grid(row=3, column=0, sticky="ew")
        ttk.Label(aba, text="Texto de cima (antes da lâmina):").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.txt_inicio = tk.Text(aba, height=9, wrap="word", font=("Segoe UI", 10), undo=True)
        self.txt_inicio.grid(row=5, column=0, sticky="ew")
        ttk.Label(aba, text="[ a lâmina entra aqui ]", foreground="#777").grid(row=6, column=0, pady=4)
        ttk.Label(aba, text="Texto de baixo (depois da lâmina; a assinatura do Outlook vem em seguida):"
                  ).grid(row=7, column=0, sticky="w")
        self.txt_fim = tk.Text(aba, height=5, wrap="word", font=("Segoe UI", 10), undo=True)
        self.txt_fim.grid(row=8, column=0, sticky="ew")
        ttk.Label(aba, text=f"Campos que são trocados pelo dado do contato: {CAMPOS_AJUDA}\n"
                            "{saudacao} vira \"bom dia\" (antes das 12h) ou \"boa tarde\".",
                  foreground="#555").grid(row=9, column=0, sticky="w", pady=8)
        botoes = ttk.Frame(aba)
        botoes.grid(row=10, column=0, sticky="w")
        ttk.Button(botoes, text="Salvar para esta campanha", command=self._salvar_msg_campanha).pack(side="left", padx=2)
        ttk.Button(botoes, text="Salvar como mensagem padrão", command=self._salvar_msg_padrao).pack(side="left", padx=2)
        ttk.Button(botoes, text="Voltar a usar a mensagem padrão nesta campanha",
                   command=self._remover_msg_campanha).pack(side="left", padx=2)

    def _carregar_mensagem_na_tela(self):
        campanha = self.var_campanha.get()
        msg = cfgmod.mensagem_da_campanha(self.cfg, campanha)
        self.var_assunto.set(msg.get("assunto", ""))
        for widget, chave in ((self.txt_inicio, "texto_inicio"), (self.txt_fim, "texto_fim")):
            widget.delete("1.0", "end")
            widget.insert("1.0", msg.get(chave, ""))
        self.lbl_msg_campanha.configure(text=f"Campanha: {campanha or '(nenhuma)'}")
        self.lbl_msg_origem.configure(
            text="Usando a mensagem própria desta campanha." if cfgmod.tem_mensagem_propria(self.cfg, campanha)
            else "Usando a mensagem padrão (salve para criar uma mensagem própria desta campanha).")

    def _salvar_msg_campanha(self):
        campanha = self.var_campanha.get()
        if not campanha:
            messagebox.showinfo("Mensagem", "Escolha uma campanha na aba Disparo.")
            return
        self.cfg["mensagens"][campanha] = self._mensagem_atual()
        cfgmod.salvar(self.cfg)
        self._carregar_mensagem_na_tela()
        messagebox.showinfo("Mensagem", f"Mensagem salva para a campanha {campanha}.")

    def _salvar_msg_padrao(self):
        self.cfg["mensagens"][cfgmod.MENSAGEM_PADRAO] = self._mensagem_atual()
        cfgmod.salvar(self.cfg)
        self._carregar_mensagem_na_tela()
        messagebox.showinfo("Mensagem", "Mensagem padrão salva.")

    def _remover_msg_campanha(self):
        campanha = self.var_campanha.get()
        if cfgmod.tem_mensagem_propria(self.cfg, campanha) and campanha != cfgmod.MENSAGEM_PADRAO:
            del self.cfg["mensagens"][campanha]
            cfgmod.salvar(self.cfg)
        self._carregar_mensagem_na_tela()

    def _oferecer_salvar_mensagem(self):
        campanha = self.var_campanha.get()
        if campanha and self._mensagem_atual() != cfgmod.mensagem_da_campanha(self.cfg, campanha):
            if messagebox.askyesno("Mensagem alterada",
                                   f"A mensagem foi alterada e não foi salva.\n"
                                   f"Salvar como mensagem da campanha {campanha}?\n\n"
                                   "(O disparo usa o texto que está na tela de qualquer forma.)"):
                self.cfg["mensagens"][campanha] = self._mensagem_atual()
                cfgmod.salvar(self.cfg)
                self._carregar_mensagem_na_tela()

    # ==================================================================
    # Aba Enviados
    # ==================================================================
    def _montar_enviados(self):
        aba = self.aba_enviados
        aba.columnconfigure(0, weight=1)
        aba.rowconfigure(1, weight=1)
        topo = ttk.Frame(aba)
        topo.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(topo, text="Buscar:").pack(side="left")
        self.var_busca = tk.StringVar()
        ent = ttk.Entry(topo, textvariable=self.var_busca, width=40)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda e: self._atualizar_enviados())
        ttk.Button(topo, text="Buscar / Atualizar", command=self._atualizar_enviados).pack(side="left")
        self.lbl_enviados = ttk.Label(topo, text="")
        self.lbl_enviados.pack(side="left", padx=12)
        ttk.Button(topo, text="Exportar para Excel...", command=self._exportar).pack(side="right", padx=2)
        ttk.Button(topo, text="Importar envios anteriores...", command=self._importar).pack(side="right", padx=2)

        quadro = ttk.Frame(aba)
        quadro.grid(row=1, column=0, sticky="nsew")
        quadro.columnconfigure(0, weight=1)
        quadro.rowconfigure(0, weight=1)
        colunas = (("data_hora", "Data/Hora", 140), ("empresa", "Empresa", 170), ("nome", "Nome", 170),
                   ("email", "E-mail", 230), ("cc", "Cópia (CC)", 170), ("campanha", "Campanha", 100),
                   ("lamina", "Lâmina", 150), ("anexo", "Anexo", 150), ("status", "Status", 80), ("erro", "Obs./Erro", 200),
                   ("versao", "Versão", 60))
        self.tv_env = ttk.Treeview(quadro, columns=[c for c, _, _ in colunas], show="headings")
        for col, titulo, larg in colunas:
            self.tv_env.heading(col, text=titulo)
            self.tv_env.column(col, width=larg, anchor="w")
        self.tv_env.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(quadro, orient="vertical", command=self.tv_env.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tv_env.configure(yscrollcommand=sb.set)
        self.tv_env.tag_configure("Erro", foreground="#b00020")
        self.tv_env.tag_configure("Importado", foreground="#666666")

    def _atualizar_enviados(self):
        linhas = self.historico.listar(self.var_busca.get().strip())
        self.tv_env.delete(*self.tv_env.get_children())
        for r in linhas:
            data = r["data_hora"] or ""
            if data:
                try:
                    data = datetime.fromisoformat(data).strftime("%d/%m/%Y %H:%M:%S")
                except ValueError:
                    pass
            self.tv_env.insert("", "end", values=(
                data, r["empresa"] or "", r["nome"] or "", r["email"], r["cc"] or "",
                r["campanha"] or "", r["lamina"] or "", r.get("anexo") or "", r["status"], r["erro"] or "",
                r.get("versao") or ""),
                tags=(r["status"],))
        enviados = sum(r["status"] == "Enviado" for r in linhas)
        self.lbl_enviados.configure(
            text=f"{len(linhas)} registros · {enviados} enviados por aqui · "
                 f"hoje: {self.historico.enviados_no_dia()}")

    def _exportar(self):
        destino = filedialog.asksaveasfilename(
            title="Exportar lista de enviados", defaultextension=".xlsx",
            initialfile=f"enviados_{datetime.now():%Y%m%d}.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not destino:
            return
        try:
            n = self.historico.exportar_xlsx(destino)
        except PermissionError:
            messagebox.showerror("Exportar", "O arquivo está aberto no Excel. Feche-o e tente de novo.")
            return
        if messagebox.askyesno("Exportar", f"{n} registros exportados.\nAbrir o arquivo agora?"):
            _abrir(Path(destino))

    def _importar(self):
        arquivo = filedialog.askopenfilename(
            title="Planilha com envios já feitos (ex.: RELATORIO / BASE-ENVIADO da macro)",
            filetypes=[("Planilhas", "*.xlsx *.xlsm *.csv"), ("Todos", "*.*")])
        if not arquivo:
            return
        try:
            abas = listar_abas(arquivo)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Importar", f"Não foi possível abrir a planilha:\n{exc}")
            return
        escolhidas = self._escolher_abas(abas) if abas else [None]
        if not escolhidas:
            return
        total_novos = total_ign = 0
        for aba in escolhidas:
            try:
                novos, ign = self.historico.importar(registros(arquivo, aba),
                                                     origem=f"Importado de {Path(arquivo).name}"
                                                            + (f" / {aba}" if aba else ""))
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Importar", f"Erro na aba {aba}:\n{exc}")
                return
            total_novos += novos
            total_ign += ign
        self._atualizar_enviados()
        messagebox.showinfo("Importar", f"{total_novos} e-mails incluídos no controle de enviados.\n"
                                        f"{total_ign} linhas ignoradas (já existentes, inválidas ou com erro).")
        if self.contatos:
            self._carregar_base()

    def _escolher_abas(self, abas: list[str]) -> list[str]:
        janela = tk.Toplevel(self)
        janela.title("Quais abas importar?")
        janela.transient(self)
        janela.grab_set()
        ttk.Label(janela, text="Selecione as abas com e-mails já enviados:", padding=8).pack(anchor="w")
        lst = tk.Listbox(janela, selectmode="multiple", height=min(12, len(abas)), exportselection=False)
        for a in abas:
            lst.insert("end", a)
            if a.upper() in ("RELATORIO", "BASE-ENVIADO", "ENVIADOS"):
                lst.selection_set("end")
        lst.pack(fill="both", expand=True, padx=8)
        resultado: list[str] = []

        def ok():
            resultado.extend(abas[i] for i in lst.curselection())
            janela.destroy()

        ttk.Button(janela, text="Importar", command=ok).pack(pady=8)
        self.wait_window(janela)
        return resultado

    # ==================================================================
    # Aba Configurações
    # ==================================================================
    def _montar_config(self):
        aba = self.aba_config
        aba.columnconfigure(1, weight=1)
        self.vars_cfg: dict[str, tk.Variable] = {}
        campos = [
            ("pasta_laminas", "Pasta das lâminas (uma subpasta por campanha)", "pasta"),
            ("pasta_anexos", "Pasta das apresentações (em branco = APRESENTAÇÃO dentro da pasta das lâminas)", "pasta"),
            ("limite_diario", "Limite de envios por dia", "int"),
            ("intervalo_minutos", "Intervalo entre envios (minutos)", "float"),
            ("email_copia", "E-mail de cópia (CC) — quem recebe cópia nos marcados", "texto"),
            ("copia_oculta", "Cópia oculta (CCO) em todos os envios (opcional)", "texto"),
            ("conta_outlook", "Conta do Outlook que envia (em branco = conta padrão)", "texto"),
            ("aba_padrao", "Aba padrão da planilha de envio", "texto"),
            ("largura_imagem_px", "Largura máxima da lâmina no e-mail (pixels)", "int"),
            ("incluir_assinatura", "Incluir a assinatura padrão do Outlook", "bool"),
            ("modo_simulacao", "Modo simulação (não envia; gera arquivos HTML para conferir)", "bool"),
        ]
        for linha, (chave, rotulo, tipo) in enumerate(campos):
            ttk.Label(aba, text=rotulo + ":").grid(row=linha, column=0, sticky="w", pady=4, padx=(0, 8))
            if tipo == "bool":
                var = tk.BooleanVar(value=bool(self.cfg.get(chave)))
                ttk.Checkbutton(aba, variable=var).grid(row=linha, column=1, sticky="w")
            else:
                var = tk.StringVar(value=str(self.cfg.get(chave, "")))
                ttk.Entry(aba, textvariable=var, width=20 if tipo in ("int", "float") else 70
                          ).grid(row=linha, column=1, sticky="w" if tipo in ("int", "float") else "ew")
                if tipo == "pasta":
                    ttk.Button(aba, text="Procurar...",
                               command=lambda v=var: v.set(filedialog.askdirectory(initialdir=v.get() or None) or v.get())
                               ).grid(row=linha, column=2, padx=4)
            self.vars_cfg[chave] = var
        self._tipos_cfg = {chave: tipo for chave, _, tipo in campos}

        botoes = ttk.Frame(aba)
        botoes.grid(row=len(campos), column=0, columnspan=3, sticky="w", pady=16)
        ttk.Button(botoes, text="Salvar configurações", command=self._salvar_config).pack(side="left", padx=2)
        ttk.Button(botoes, text="Abrir pasta de dados (histórico / simulação)",
                   command=lambda: (PASTA_DADOS.mkdir(exist_ok=True), _abrir(PASTA_DADOS))).pack(side="left", padx=2)
        ttk.Label(aba, foreground="#555", justify="left", text=(
            f"Versão do programa: {__version__}\n"
            f"Histórico de enviados: {ARQUIVO_HISTORICO}\n"
            f"Configurações: {cfgmod.ARQUIVO_CONFIG}")).grid(row=len(campos) + 1, column=0, columnspan=3, sticky="w")

    def _salvar_config(self):
        novo = {}
        for chave, var in self.vars_cfg.items():
            tipo = self._tipos_cfg[chave]
            valor = var.get()
            try:
                if tipo == "int":
                    valor = int(str(valor).strip())
                    if valor <= 0:
                        raise ValueError
                elif tipo == "float":
                    valor = float(str(valor).strip().replace(",", "."))
                    if valor < 0:
                        raise ValueError
                elif tipo != "bool":
                    valor = str(valor).strip()
            except ValueError:
                messagebox.showerror("Configurações", f"Valor inválido em '{chave}': {var.get()}")
                return
            novo[chave] = valor
        for chave in ("email_copia", "copia_oculta"):
            enderecos = [x.strip() for x in novo[chave].replace(",", ";").split(";") if x.strip()]
            if any(not email_valido(x) for x in enderecos):
                messagebox.showerror("Configurações", f"E-mail inválido em '{chave}'.")
                return
        pasta_mudou = (novo["pasta_laminas"] != self.cfg.get("pasta_laminas")
                       or novo["pasta_anexos"] != self.cfg.get("pasta_anexos"))
        copia_mudou = novo["email_copia"] != self.cfg.get("email_copia")
        self.cfg.update(novo)
        cfgmod.salvar(self.cfg)
        if copia_mudou and self.var_cc.get().strip() != novo["email_copia"]:
            self.var_cc.set(novo["email_copia"])
        if pasta_mudou:
            self._recarregar_campanhas(self.var_campanha.get())
        self._atualizar_contadores()
        messagebox.showinfo("Configurações", "Configurações salvas.")

    # ==================================================================
    def _fechar(self):
        if self._em_disparo():
            if not messagebox.askyesno("Sair", "O disparo está em andamento. Interromper e sair?"):
                return
            self.disparo.parar()
            manter_pc_acordado(False)
        self.destroy()

    def report_callback_exception(self, exc, val, tb):  # noqa: D401 - API do tkinter
        detalhe = "".join(traceback.format_exception(exc, val, tb))
        self._log(f"ERRO: {val}")
        messagebox.showerror("Erro inesperado", f"{val}\n\n{detalhe[-1500:]}")


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - só melhora a nitidez
            pass
    App().mainloop()
