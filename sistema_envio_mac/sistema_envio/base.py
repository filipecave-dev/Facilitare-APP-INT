"""Leitura da lista de envio e verificação de duplicados.

A base é uma planilha (``.xlsx``/``.xlsm``/``.csv``) com, no mínimo, as colunas
**Empresa**, **Nome** e **E-mail** (os títulos são reconhecidos por
aproximação: "Nome Completo", "E-mail Principal" etc.). Uma coluna opcional
**Cópia**/**CC** com "S"/"X"/"Sim" já deixa o contato marcado para cópia.

Cada linha vira um :class:`Contato` com uma situação:

- ``pendente``   — pronto para envio;
- ``duplicado``  — o mesmo e-mail aparece numa linha anterior da base;
- ``ja_enviado`` — o e-mail já está no histórico de enviados;
- ``invalido``   — e-mail vazio/mal formado ou faltando nome/empresa;
- ``enviado``    — enviado nesta sessão.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Optional

PENDENTE = "pendente"
DUPLICADO = "duplicado"
JA_ENVIADO = "ja_enviado"
INVALIDO = "invalido"
ENVIADO = "enviado"

_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+'\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_SIM = {"s", "sim", "x", "1", "true", "verdadeiro", "cc", "copia", "yes"}


@dataclass
class Contato:
    linha: int
    empresa: str
    nome: str
    email: str
    situacao: str = PENDENTE
    detalhe: str = ""
    enviar: bool = False
    cc: bool = False
    # Reenvio autorizado manualmente para um e-mail que já recebeu lâmina.
    forcar: bool = False

    @property
    def email_norm(self) -> str:
        return normalizar_email(self.email)

    @property
    def selecionavel(self) -> bool:
        return self.situacao in (PENDENTE, JA_ENVIADO)


@dataclass
class Resumo:
    total: int = 0
    pendentes: int = 0
    ja_enviados: int = 0
    invalidos: int = 0
    # e-mail -> números das linhas em que aparece (só os repetidos)
    duplicados: dict[str, list[int]] = field(default_factory=dict)


# -- limpeza ---------------------------------------------------------------

def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def limpar_texto(valor) -> str:
    """Remove lixo de exportação (``_x000D_``, quebras, tabs) e espaços extras."""
    if valor is None:
        return ""
    texto = str(valor).replace("_x000D_", " ")
    return " ".join(texto.split())


def limpar_email(valor) -> str:
    texto = limpar_texto(valor)
    if texto.lower().startswith("mailto:"):
        texto = texto[7:]
    return texto.strip(" <>;,").replace(" ", "")


def normalizar_email(valor) -> str:
    return limpar_email(valor).lower()


def email_valido(email: str) -> bool:
    return bool(_RE_EMAIL.match(email or ""))


def _titulo(valor) -> str:
    return _sem_acento(limpar_texto(valor)).lower()


# -- leitura de planilhas --------------------------------------------------

def listar_abas(caminho: str) -> list[str]:
    if Path(caminho).suffix.lower() == ".csv":
        return []
    from openpyxl import load_workbook
    wb = load_workbook(caminho, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _linhas_csv(caminho: str) -> list[tuple]:
    bruto = Path(caminho).read_bytes()
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t")
    except csv.Error:
        dialeto = csv.excel
        dialeto.delimiter = ";"
    return [tuple(r) for r in csv.reader(texto.splitlines(), dialeto)]


def ler_linhas(caminho: str, aba: Optional[str] = None) -> list[tuple]:
    """Todas as linhas (tuplas de valores) da aba ou do CSV."""
    if Path(caminho).suffix.lower() == ".csv":
        return _linhas_csv(caminho)
    from openpyxl import load_workbook
    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        ws = wb[aba] if aba and aba in wb.sheetnames else wb.worksheets[0]
        return [tuple(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


# Títulos reconhecidos para cada coluna (sem acento, minúsculos). A ordem das
# chaves importa: "sobrenome" antes de "nome", "nome da empresa" antes de "nome".
_TITULOS: list[tuple[str, tuple[str, ...]]] = [
    ("copia", ("copia (cc)", "copia", "cc", "com copia")),
    ("sobrenome", ("sobrenome", "ultimo nome", "last name", "surname")),
    ("empresa", ("empresa", "nome da empresa", "razao social", "nome fantasia", "companhia",
                 "company", "organizacao", "organization", "instituicao", "cliente empresa")),
    ("email", ("e-mail", "email", "e mail", "endereco de e-mail", "endereco de email",
               "correio eletronico", "mail")),
    ("nome", ("nome", "nome completo", "nome do cliente", "nome do contato", "contato",
              "primeiro nome", "cliente", "responsavel", "pessoa", "destinatario",
              "name", "first name", "full name")),
    ("data", ("data", "data de envio", "data envio", "date")),
    ("hora", ("hora", "horario", "time")),
    ("status", ("status", "situacao")),
]
_IGNORAR_TITULO = ("oculta", "cco", "bcc", "mensagem", "assunto", "complemento", "caminho",
                   "imagem", "cargo", "telefone", "celular", "fone", "site", "linkedin")
CAMPOS_BASE = ("email", "nome", "empresa", "copia")


def _qualidade(titulo: str, apelido: str) -> int:
    """3 = título igual, 2 = começa com o apelido, 1 = contém a palavra."""
    if titulo == apelido:
        return 3
    if titulo.startswith(apelido + " ") or titulo.startswith(apelido + "("):
        return 2
    return 1 if re.search(rf"(^|[^a-z]){re.escape(apelido)}([^a-z]|$)", titulo) else 0


def _classificar(titulos: list[str]) -> dict[str, int]:
    """Índice da melhor coluna para cada campo, pelo título (qualquer ordem)."""
    melhor: dict[str, tuple[int, int]] = {}  # campo -> (qualidade, -indice)
    usados: dict[int, str] = {}
    for campo, apelidos in _TITULOS:
        for j, t in enumerate(titulos):
            if not t or j in usados:
                continue
            if any(p in t for p in _IGNORAR_TITULO) and not (campo == "copia" and "oculta" not in t):
                continue
            q = max(_qualidade(t, a) for a in apelidos)
            if q and (campo not in melhor or (q, -j) > melhor[campo]):
                melhor[campo] = (q, -j)
        if campo in melhor:
            usados[-melhor[campo][1]] = campo
    return {campo: -idx for campo, (_, idx) in melhor.items()}


def _coluna_de_emails(linhas: list[tuple]) -> Optional[int]:
    """Coluna em que a maioria das células tem cara de e-mail (fallback)."""
    contagem: dict[int, int] = {}
    preenchidas: dict[int, int] = {}
    for linha in linhas[:60]:
        for j, v in enumerate(linha):
            texto = limpar_email(v)
            if texto:
                preenchidas[j] = preenchidas.get(j, 0) + 1
                if email_valido(texto):
                    contagem[j] = contagem.get(j, 0) + 1
    candidatas = [(n, -j) for j, n in contagem.items() if n >= max(1, preenchidas[j] // 2)]
    return -max(candidatas)[1] if candidatas else None


def mapear_colunas(linhas: list[tuple]) -> tuple[int, dict[str, int]]:
    """Acha a linha de títulos (entre as 20 primeiras) e a coluna de cada
    campo pelo **título**, em qualquer ordem. Retorna
    ``(indice_da_linha_de_titulo, colunas)``; o índice é ``-1`` quando a
    planilha não tem linha de títulos."""
    melhor_linha, melhor_cols, melhor_pontos = None, {}, 0
    for i, linha in enumerate(linhas[:20]):
        cols = _classificar([_titulo(v) for v in linha])
        if any(email_valido(limpar_email(v)) for v in linha):
            continue  # linha de dados, não de títulos
        pontos = sum(c in cols for c in ("email", "nome", "empresa")) * 2 + ("email" in cols)
        if pontos > melhor_pontos:
            melhor_linha, melhor_cols, melhor_pontos = i, cols, pontos
    if melhor_linha is not None and "email" in melhor_cols:
        return melhor_linha, melhor_cols
    # Sem título de e-mail: procura a coluna pelos valores.
    j = _coluna_de_emails(linhas[(melhor_linha or 0):])
    if j is None:
        raise ValueError(
            "Não encontrei a coluna de E-mail na planilha. Confira se a aba "
            "tem os títulos Empresa / Nome / E-mail."
        )
    if melhor_linha is None:
        # Títulos não reconhecidos (ex.: "Col1"): a linha logo acima do
        # primeiro e-mail é tratada como títulos, se existir e não estiver vazia.
        primeiro = next((k for k, l in enumerate(linhas)
                         if email_valido(limpar_email(l[j] if j < len(l) else None))), 0)
        acima = primeiro - 1
        if acima >= 0 and any(limpar_texto(v) for v in linhas[acima]):
            return acima, {"email": j}
        return -1, {"email": j}
    return melhor_linha, {**melhor_cols, "email": j}


def _valor(linha: tuple, colunas: dict[str, int], chave: str):
    j = colunas.get(chave)
    return linha[j] if j is not None and j < len(linha) else None


@dataclass
class Cabecalho:
    """Linha de títulos encontrada e colunas usadas para cada campo."""
    linha_titulo: int  # número da linha na planilha (0 = sem títulos)
    titulos: list[str]
    colunas: dict[str, int]

    def descricao(self, campo: str) -> str:
        j = self.colunas.get(campo)
        if j is None:
            return "(nenhuma)"
        titulo = self.titulos[j] if j < len(self.titulos) and self.titulos[j] else ""
        return f"{letra_coluna(j)} - {titulo}" if titulo else letra_coluna(j)


def letra_coluna(j: int) -> str:
    letras = ""
    j += 1
    while j:
        j, r = divmod(j - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def ler_base(caminho: str, aba: Optional[str] = None,
             colunas: Optional[dict[str, Optional[int]]] = None) -> tuple[list[dict], Cabecalho]:
    """Linhas da planilha como dicionários (empresa, nome, email, copia,
    data, status, linha) e o cabeçalho usado.

    As colunas são achadas pelo título, em qualquer ordem. ``colunas``
    permite escolher manualmente a coluna de um campo (índice a partir de 0;
    ``None`` = nenhuma). Linhas totalmente vazias são ignoradas.
    """
    linhas = ler_linhas(caminho, aba)
    if not linhas:
        return [], Cabecalho(0, [], {})
    inicio, detectadas = mapear_colunas(linhas)
    cols = dict(detectadas)
    for campo, j in (colunas or {}).items():
        if j is None:
            cols.pop(campo, None)
        else:
            cols[campo] = j
    if "email" not in cols:
        raise ValueError("Escolha qual coluna tem o E-mail.")
    largura = max((len(l) for l in linhas[:max(inicio, 0) + 50]), default=0)
    titulos = [limpar_texto(v) for v in linhas[inicio]] if inicio >= 0 else []
    titulos += [""] * (largura - len(titulos))
    cab = Cabecalho(inicio + 1, titulos, cols)

    saida = []
    for n, linha in enumerate(linhas[inicio + 1:], start=inicio + 2):
        nome = limpar_texto(_valor(linha, cols, "nome"))
        sobrenome = limpar_texto(_valor(linha, cols, "sobrenome"))
        if sobrenome and sobrenome.casefold() not in nome.casefold():
            nome = f"{nome} {sobrenome}".strip()
        reg = {
            "linha": n,
            "empresa": limpar_texto(_valor(linha, cols, "empresa")),
            "nome": nome,
            "email": limpar_email(_valor(linha, cols, "email")),
            "copia": limpar_texto(_valor(linha, cols, "copia")),
            "data": _data_hora(_valor(linha, cols, "data"), _valor(linha, cols, "hora")),
            "status": limpar_texto(_valor(linha, cols, "status")),
        }
        if reg["email"] or reg["nome"] or reg["empresa"]:
            saida.append(reg)
    return saida, cab


def registros(caminho: str, aba: Optional[str] = None,
              colunas: Optional[dict[str, Optional[int]]] = None) -> list[dict]:
    """Atalho de :func:`ler_base` que devolve só as linhas."""
    return ler_base(caminho, aba, colunas)[0]


def _data_hora(data, hora) -> Optional[datetime]:
    if isinstance(data, datetime):
        base = data
    elif isinstance(data, date):
        base = datetime.combine(data, time())
    elif isinstance(data, str) and data.strip():
        base = None
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                base = datetime.strptime(data.strip(), formato)
                break
            except ValueError:
                continue
        if base is None:
            return None
    else:
        return None
    if isinstance(hora, time) and base.time() == time():
        base = datetime.combine(base.date(), hora)
    elif isinstance(hora, str) and base.time() == time():
        try:
            base = datetime.combine(base.date(), time.fromisoformat(hora.strip()))
        except ValueError:
            pass
    return base


# -- análise ---------------------------------------------------------------

def analisar(regs: Iterable[dict], ja_enviados: dict[str, Optional[str]]) -> tuple[list[Contato], Resumo]:
    """Classifica cada linha e aponta duplicados.

    ``ja_enviados`` mapeia e-mail normalizado -> data/hora do envio anterior
    (texto ``AAAA-MM-DD HH:MM:SS`` ou ``None`` quando a data é desconhecida).
    """
    contatos: list[Contato] = []
    resumo = Resumo()
    primeira_linha: dict[str, int] = {}
    for reg in regs:
        c = Contato(linha=reg["linha"], empresa=reg["empresa"], nome=reg["nome"],
                    email=limpar_email(reg["email"]), cc=_titulo(reg.get("copia")) in _SIM)
        norm = c.email_norm
        if not c.email:
            c.situacao, c.detalhe = INVALIDO, "Sem e-mail"
        elif not email_valido(c.email):
            c.situacao, c.detalhe = INVALIDO, "E-mail inválido"
        elif norm in primeira_linha:
            c.situacao = DUPLICADO
            c.detalhe = f"Duplicado da linha {primeira_linha[norm]}"
            resumo.duplicados.setdefault(norm, [primeira_linha[norm]]).append(c.linha)
        else:
            primeira_linha[norm] = c.linha
            if not c.nome or not c.empresa:
                c.situacao = INVALIDO
                falta = " e ".join(x for x, v in (("nome", c.nome), ("empresa", c.empresa)) if not v)
                c.detalhe = f"Falta {falta}"
            elif norm in ja_enviados:
                c.situacao = JA_ENVIADO
                c.detalhe = "Já enviado" + _quando(ja_enviados[norm])
            else:
                c.situacao, c.enviar = PENDENTE, True
        if not c.selecionavel or c.situacao == JA_ENVIADO:
            c.cc = False
        contatos.append(c)

    resumo.total = len(contatos)
    resumo.pendentes = sum(c.situacao == PENDENTE for c in contatos)
    resumo.ja_enviados = sum(c.situacao == JA_ENVIADO for c in contatos)
    resumo.invalidos = sum(c.situacao == INVALIDO for c in contatos)
    return contatos, resumo


def _quando(data_hora: Optional[str]) -> str:
    if not data_hora:
        return " (envio anterior)"
    try:
        return " em " + datetime.fromisoformat(data_hora).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return f" em {data_hora}"
