"""Cadastro de empresas (clientes) do Informativo.

Cada **empresa** é um cliente cadastrado dentro do sistema. Além do nome de
cadastro, cada empresa personaliza:

* **Nome da solução** (``nome_solucao``) — como a solução/o informativo é
  chamado para aquele cliente (a marca do boletim que ele envia).
* **Assunto do e-mail** (``assunto_email``) — o assunto que sai no e-mail
  enviado por aquele cliente.

Opcionalmente, também uma cor de destaque própria (``tema_primary``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .db import Database

# Tamanho máximo do template de fundo do informativo (2 MB).
TEMPLATE_MAX_BYTES = 2 * 1024 * 1024
# Tamanho máximo do logo (512 KB) e dimensão recomendada de exibição.
LOGO_MAX_BYTES = 512 * 1024
LOGO_ALTURA_BARRA = 40   # px — altura na barra do informativo
LOGO_LARGURA_MAX = 220   # px — largura máxima recomendada

# 4 modelos de fonte (tipografia) comuns em informativos corporativos.
# Cada modelo é uma pilha ``font-family`` pronta para uso no informativo/e-mail.
MODELOS_FONTE = {
    "classica": {
        "rotulo": "Clássica (serifada)",
        "familia": "Georgia, 'Times New Roman', Times, serif",
    },
    "moderna": {
        "rotulo": "Moderna (sem serifa)",
        "familia": "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    },
    "corporativa": {
        "rotulo": "Corporativa (Arial)",
        "familia": "Arial, 'Helvetica Neue', Helvetica, sans-serif",
    },
    "editorial": {
        "rotulo": "Editorial (Calibri/Candara)",
        "familia": "Calibri, Candara, 'Segoe UI', Optima, sans-serif",
    },
}
MODELO_FONTE_PADRAO = "moderna"


def familia_do_modelo(modelo: Optional[str]) -> str:
    """Devolve a pilha ``font-family`` do modelo escolhido (ou o padrão)."""
    dados = MODELOS_FONTE.get((modelo or "").strip() or MODELO_FONTE_PADRAO)
    if not dados:
        dados = MODELOS_FONTE[MODELO_FONTE_PADRAO]
    return dados["familia"]


@dataclass
class Empresa:
    """Registro da tabela ``empresas``."""

    id: int
    nome: str
    nome_solucao: str
    assunto_email: str = ""
    contato_email: Optional[str] = None
    tema_primary: Optional[str] = None
    fonte_modelo: Optional[str] = None
    template_nome: Optional[str] = None
    template_mime: Optional[str] = None
    tem_template: bool = False
    logo_nome: Optional[str] = None
    logo_mime: Optional[str] = None
    tem_logo: bool = False
    ativa: bool = True
    criado_em: Optional[str] = None
    atualizado_em: Optional[str] = None


def _row_para_empresa(row: dict) -> Empresa:
    return Empresa(
        id=row["id"],
        nome=row["nome"],
        nome_solucao=row["nome_solucao"],
        assunto_email=row.get("assunto_email") or "",
        contato_email=row.get("contato_email"),
        tema_primary=row.get("tema_primary"),
        fonte_modelo=row.get("fonte_modelo"),
        template_nome=row.get("template_nome"),
        template_mime=row.get("template_mime"),
        tem_template=bool(row.get("template_dados")),
        logo_nome=row.get("logo_nome"),
        logo_mime=row.get("logo_mime"),
        tem_logo=bool(row.get("logo_dados")),
        ativa=bool(row.get("ativa", 1)),
        criado_em=row.get("criado_em"),
        atualizado_em=row.get("atualizado_em"),
    )


class EmpresaRepository:
    """Acesso à tabela ``empresas`` (CRUD)."""

    def __init__(self, db: Database):
        self.db = db

    def _agora(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- leitura ------------------------------------------------------------
    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM empresas") or 0)

    def get(self, empresa_id: int) -> Optional[Empresa]:
        row = self.db.query_one("SELECT * FROM empresas WHERE id = ?", (empresa_id,))
        return _row_para_empresa(row) if row else None

    def existe_nome(self, nome: str, ignorar_id: Optional[int] = None) -> bool:
        if ignorar_id is None:
            total = self.db.scalar(
                "SELECT COUNT(*) FROM empresas WHERE LOWER(nome) = LOWER(?)",
                (nome.strip(),),
            )
        else:
            total = self.db.scalar(
                "SELECT COUNT(*) FROM empresas WHERE LOWER(nome) = LOWER(?) AND id <> ?",
                (nome.strip(), ignorar_id),
            )
        return (total or 0) > 0

    def listar(self, *, apenas_ativas: bool = False) -> list[Empresa]:
        sql = "SELECT * FROM empresas"
        if apenas_ativas:
            sql += " WHERE ativa = 1"
        sql += " ORDER BY LOWER(nome) ASC"
        return [_row_para_empresa(r) for r in self.db.query_all(sql)]

    # -- escrita ------------------------------------------------------------
    def criar(
        self,
        nome: str,
        *,
        nome_solucao: Optional[str] = None,
        assunto_email: Optional[str] = None,
        contato_email: Optional[str] = None,
        tema_primary: Optional[str] = None,
        ativa: bool = True,
    ) -> Empresa:
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("O nome da empresa é obrigatório.")
        if self.existe_nome(nome):
            raise ValueError(f"Já existe uma empresa com o nome {nome!r}.")
        # Nome da solução: por padrão, o próprio nome da empresa.
        nome_solucao = (nome_solucao or "").strip() or nome
        # Assunto do e-mail: por padrão, acompanha o nome da solução.
        assunto_email = (assunto_email or "").strip() or nome_solucao
        agora = self._agora()
        novo_id = self.db.insert(
            "INSERT INTO empresas (nome, nome_solucao, assunto_email, contato_email, "
            "tema_primary, ativa, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nome, nome_solucao, assunto_email, contato_email, tema_primary,
             1 if ativa else 0, agora, agora),
        )
        self.db.commit()
        empresa = self.get(novo_id)
        assert empresa is not None
        return empresa

    def obter_por_nome(self, nome: str) -> Optional[Empresa]:
        row = self.db.query_one(
            "SELECT * FROM empresas WHERE LOWER(nome) = LOWER(?)", ((nome or "").strip(),)
        )
        return _row_para_empresa(row) if row else None

    def obter_ou_criar(self, nome: str, **kwargs) -> Empresa:
        """Devolve a empresa pelo nome, criando-a se ainda não existir."""
        existente = self.obter_por_nome(nome)
        if existente is not None:
            return existente
        return self.criar(nome, **kwargs)

    def atualizar(self, empresa_id: int, **campos) -> None:
        permitidos = {
            "nome", "nome_solucao", "assunto_email",
            "contato_email", "tema_primary", "fonte_modelo", "ativa",
        }
        empresa = self.get(empresa_id)
        if empresa is None:
            raise ValueError("Empresa não encontrada.")
        if "nome" in campos:
            novo = (campos["nome"] or "").strip()
            if not novo:
                raise ValueError("O nome da empresa é obrigatório.")
            if self.existe_nome(novo, ignorar_id=empresa_id):
                raise ValueError(f"Já existe uma empresa com o nome {novo!r}.")
        nome_ref = (campos.get("nome") or empresa.nome).strip()
        if "nome_solucao" in campos:
            # Nome da solução vazio volta a acompanhar o nome da empresa.
            campos["nome_solucao"] = (campos["nome_solucao"] or "").strip() or nome_ref
        if "assunto_email" in campos:
            # Assunto vazio volta a acompanhar o nome da solução.
            solucao_ref = (
                campos.get("nome_solucao") or empresa.nome_solucao or nome_ref
            ).strip()
            campos["assunto_email"] = (campos["assunto_email"] or "").strip() or solucao_ref
        sets, params = [], []
        for chave, valor in campos.items():
            if chave not in permitidos:
                continue
            if chave == "ativa":
                valor = 1 if valor else 0
            sets.append(f"{chave} = ?")
            params.append(valor)
        if not sets:
            return
        sets.append("atualizado_em = ?")
        params.append(self._agora())
        params.append(empresa_id)
        self.db.execute(
            f"UPDATE empresas SET {', '.join(sets)} WHERE id = ?", params
        )
        self.db.commit()

    # -- template de fundo do informativo ----------------------------------
    def salvar_template(self, empresa_id: int, nome: str, mime: str,
                        dados: bytes) -> None:
        """Guarda o arquivo de template (fundo do informativo), até 2 MB.

        O binário é persistido como base64 em ``template_dados`` para ser
        portável entre SQLite e PostgreSQL sem depender de tipos BLOB/BYTEA.
        """
        import base64

        if not dados:
            raise ValueError("Arquivo de template vazio.")
        if len(dados) > TEMPLATE_MAX_BYTES:
            raise ValueError("O template excede o limite de 2 MB.")
        b64 = base64.b64encode(dados).decode("ascii")
        self.db.execute(
            "UPDATE empresas SET template_nome = ?, template_mime = ?, "
            "template_dados = ?, atualizado_em = ? WHERE id = ?",
            ((nome or "template").strip(), (mime or "application/octet-stream"),
             b64, self._agora(), empresa_id),
        )
        self.db.commit()

    def remover_template(self, empresa_id: int) -> None:
        self.db.execute(
            "UPDATE empresas SET template_nome = NULL, template_mime = NULL, "
            "template_dados = NULL, atualizado_em = ? WHERE id = ?",
            (self._agora(), empresa_id),
        )
        self.db.commit()

    def obter_template(self, empresa_id: int):
        """Devolve ``(nome, mime, bytes)`` do template, ou ``None``."""
        import base64

        row = self.db.query_one(
            "SELECT template_nome, template_mime, template_dados "
            "FROM empresas WHERE id = ?", (empresa_id,),
        )
        if not row or not row.get("template_dados"):
            return None
        try:
            dados = base64.b64decode(row["template_dados"])
        except Exception:  # noqa: BLE001
            return None
        return (row.get("template_nome") or "template",
                row.get("template_mime") or "application/octet-stream", dados)

    # -- logo do informativo (exibido na barra, até 512 KB) ----------------
    def salvar_logo(self, empresa_id: int, nome: str, mime: str,
                    dados: bytes) -> None:
        import base64

        if not dados:
            raise ValueError("Arquivo de logo vazio.")
        if len(dados) > LOGO_MAX_BYTES:
            raise ValueError("O logo excede o limite de 512 KB.")
        b64 = base64.b64encode(dados).decode("ascii")
        self.db.execute(
            "UPDATE empresas SET logo_nome = ?, logo_mime = ?, "
            "logo_dados = ?, atualizado_em = ? WHERE id = ?",
            ((nome or "logo").strip(), (mime or "application/octet-stream"),
             b64, self._agora(), empresa_id),
        )
        self.db.commit()

    def remover_logo(self, empresa_id: int) -> None:
        self.db.execute(
            "UPDATE empresas SET logo_nome = NULL, logo_mime = NULL, "
            "logo_dados = NULL, atualizado_em = ? WHERE id = ?",
            (self._agora(), empresa_id),
        )
        self.db.commit()

    def obter_logo(self, empresa_id: int):
        """Devolve ``(nome, mime, bytes)`` do logo, ou ``None``."""
        import base64

        row = self.db.query_one(
            "SELECT logo_nome, logo_mime, logo_dados FROM empresas WHERE id = ?",
            (empresa_id,),
        )
        if not row or not row.get("logo_dados"):
            return None
        try:
            dados = base64.b64decode(row["logo_dados"])
        except Exception:  # noqa: BLE001
            return None
        return (row.get("logo_nome") or "logo",
                row.get("logo_mime") or "application/octet-stream", dados)

    def alternar_ativa(self, empresa_id: int) -> None:
        self.db.execute(
            "UPDATE empresas SET ativa = 1 - ativa, atualizado_em = ? WHERE id = ?",
            (self._agora(), empresa_id),
        )
        self.db.commit()

    def remover(self, empresa_id: int) -> None:
        self.db.execute("DELETE FROM empresas WHERE id = ?", (empresa_id,))
        self.db.commit()
