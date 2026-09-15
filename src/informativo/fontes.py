"""Cadastro das fontes de informação a buscar.

Uma *fonte* é um provedor de onde o Informativo captura informações (site,
portal, órgão oficial etc.). O cadastro inicial vem da aba **Fontes** da
planilha de referência (80 fontes), empacotada em ``seed_data/fontes_seed.json``.

Colunas de negócio expostas na tela de Gerenciar Fontes:
Fonte, URL (site), Categoria, País/Região, Idioma, Relevância, Prioridade,
Ativa e Data de inclusão.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .db import Database

_SEED_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "seed_data", "fontes_seed.json"
)


@dataclass
class Fonte:
    """Registro da tabela ``fontes``."""

    id: int
    nome: str
    url: str
    categoria: Optional[str] = None
    regiao: Optional[str] = None
    idioma: Optional[str] = None
    relevancia: int = 3
    prioridade: int = 3
    empresa_id: Optional[int] = None
    ativa: bool = True
    criado_em: Optional[str] = None
    atualizado_em: Optional[str] = None

    @property
    def global_(self) -> bool:
        return self.empresa_id is None


def _row_para_fonte(row: dict) -> Fonte:
    return Fonte(
        id=row["id"],
        nome=row["nome"],
        url=row["url"],
        categoria=row.get("categoria"),
        regiao=row.get("regiao"),
        idioma=row.get("idioma"),
        relevancia=int(row.get("relevancia", 3) or 3),
        prioridade=int(row.get("prioridade", 3) or 3),
        empresa_id=row.get("empresa_id"),
        ativa=bool(row.get("ativa", 1)),
        criado_em=row.get("criado_em"),
        atualizado_em=row.get("atualizado_em"),
    )


def _normalizar_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("A URL da fonte é obrigatória.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def carregar_seed() -> list[dict]:
    """Lê o conjunto de fontes-semente (aba Fontes da planilha)."""
    with open(_SEED_PATH, encoding="utf-8") as f:
        return json.load(f)


class FonteRepository:
    """Acesso à tabela ``fontes`` (CRUD, importação em massa e filtros)."""

    def __init__(self, db: Database):
        self.db = db

    def _agora(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- leitura ------------------------------------------------------------
    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM fontes") or 0)

    def get(self, fonte_id: int) -> Optional[Fonte]:
        row = self.db.query_one("SELECT * FROM fontes WHERE id = ?", (fonte_id,))
        return _row_para_fonte(row) if row else None

    def existe_url(self, url: str) -> bool:
        total = self.db.scalar(
            "SELECT COUNT(*) FROM fontes WHERE url = ?", (_normalizar_url(url),)
        )
        return (total or 0) > 0

    def listar(
        self,
        *,
        busca: Optional[str] = None,
        categoria: Optional[str] = None,
        regiao: Optional[str] = None,
        apenas_ativas: bool = False,
        escopo=None,
    ) -> list[Fonte]:
        """Lista fontes. ``escopo`` isola por empresa:

        * ``None`` — todas (visão da plataforma);
        * ``("visiveis", empresa_id)`` — globais + as privadas da empresa;
        * ``("privadas", empresa_id)`` — só as privadas da empresa;
        * ``("global",)`` — só o catálogo global.
        """
        clausulas = []
        params: list = []
        if escopo:
            if escopo[0] == "visiveis":
                clausulas.append("(empresa_id IS NULL OR empresa_id = ?)")
                params.append(escopo[1])
            elif escopo[0] == "privadas":
                clausulas.append("empresa_id = ?")
                params.append(escopo[1])
            elif escopo[0] == "global":
                clausulas.append("empresa_id IS NULL")
        if busca:
            clausulas.append("(LOWER(nome) LIKE LOWER(?) OR LOWER(url) LIKE LOWER(?))")
            termo = f"%{busca.strip()}%"
            params += [termo, termo]
        if categoria:
            clausulas.append("categoria = ?")
            params.append(categoria)
        if regiao:
            clausulas.append("regiao = ?")
            params.append(regiao)
        if apenas_ativas:
            clausulas.append("ativa = 1")
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        sql = (
            "SELECT * FROM fontes" + where +
            " ORDER BY prioridade DESC, relevancia DESC, LOWER(nome) ASC"
        )
        return [_row_para_fonte(r) for r in self.db.query_all(sql, params)]

    def categorias(self) -> list[str]:
        rows = self.db.query_all(
            "SELECT DISTINCT categoria FROM fontes "
            "WHERE categoria IS NOT NULL AND categoria <> '' ORDER BY categoria"
        )
        return [r["categoria"] for r in rows]

    def regioes(self) -> list[str]:
        rows = self.db.query_all(
            "SELECT DISTINCT regiao FROM fontes "
            "WHERE regiao IS NOT NULL AND regiao <> '' ORDER BY regiao"
        )
        return [r["regiao"] for r in rows]

    def resumo(self) -> dict:
        """Métricas rápidas para o painel principal."""
        total = self.count()
        ativas = int(self.db.scalar("SELECT COUNT(*) FROM fontes WHERE ativa = 1") or 0)
        n_categorias = int(
            self.db.scalar(
                "SELECT COUNT(DISTINCT categoria) FROM fontes "
                "WHERE categoria IS NOT NULL AND categoria <> ''"
            )
            or 0
        )
        n_regioes = int(
            self.db.scalar(
                "SELECT COUNT(DISTINCT regiao) FROM fontes "
                "WHERE regiao IS NOT NULL AND regiao <> ''"
            )
            or 0
        )
        return {
            "total": total,
            "ativas": ativas,
            "inativas": total - ativas,
            "categorias": n_categorias,
            "regioes": n_regioes,
        }

    # -- escrita ------------------------------------------------------------
    def criar(
        self,
        nome: str,
        url: str,
        *,
        categoria: Optional[str] = None,
        regiao: Optional[str] = None,
        idioma: Optional[str] = None,
        relevancia: int = 3,
        prioridade: int = 3,
        empresa_id: Optional[int] = None,
        ativa: bool = True,
    ) -> Fonte:
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("O nome da fonte é obrigatório.")
        url = _normalizar_url(url)
        if self.existe_url(url):
            raise ValueError(f"Já existe uma fonte com a URL {url!r}.")
        agora = self._agora()
        novo_id = self.db.insert(
            "INSERT INTO fontes (nome, url, categoria, regiao, idioma, "
            "relevancia, prioridade, empresa_id, ativa, criado_em, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nome, url, categoria, regiao, idioma,
                _clamp(relevancia), _clamp(prioridade),
                empresa_id, 1 if ativa else 0, agora, agora,
            ),
        )
        self.db.commit()
        fonte = self.get(novo_id)
        assert fonte is not None
        return fonte

    def atualizar(self, fonte_id: int, **campos) -> None:
        permitidos = {
            "nome", "url", "categoria", "regiao", "idioma",
            "relevancia", "prioridade", "ativa",
        }
        # URL: normaliza e impede duplicar a de outra fonte.
        if "url" in campos:
            url = _normalizar_url(campos["url"])
            outra = self.db.scalar(
                "SELECT COUNT(*) FROM fontes WHERE url = ? AND id <> ?",
                (url, fonte_id),
            )
            if (outra or 0) > 0:
                raise ValueError(f"Já existe outra fonte com a URL {url!r}.")
            campos["url"] = url
        sets, params = [], []
        for chave, valor in campos.items():
            if chave not in permitidos:
                continue
            if chave in ("relevancia", "prioridade"):
                valor = _clamp(int(valor))
            if chave == "ativa":
                valor = 1 if valor else 0
            if chave == "nome":
                valor = (valor or "").strip()
                if not valor:
                    raise ValueError("O nome da fonte é obrigatório.")
            sets.append(f"{chave} = ?")
            params.append(valor)
        if not sets:
            return
        sets.append("atualizado_em = ?")
        params.append(self._agora())
        params.append(fonte_id)
        self.db.execute(
            f"UPDATE fontes SET {', '.join(sets)} WHERE id = ?", params
        )
        self.db.commit()

    def alternar_ativa(self, fonte_id: int) -> None:
        self.db.execute(
            "UPDATE fontes SET ativa = 1 - ativa, atualizado_em = ? WHERE id = ?",
            (self._agora(), fonte_id),
        )
        self.db.commit()

    def definir_ativa_em_massa(self, ativa: bool, *, escopo=None) -> None:
        """Ativa/desativa fontes em massa. ``escopo`` como em :meth:`listar`."""
        clausula, params = "", []
        if escopo:
            if escopo[0] == "privadas":
                clausula = " WHERE empresa_id = ?"
                params = [escopo[1]]
            elif escopo[0] == "global":
                clausula = " WHERE empresa_id IS NULL"
            elif escopo[0] == "visiveis":
                clausula = " WHERE empresa_id IS NULL OR empresa_id = ?"
                params = [escopo[1]]
        self.db.execute(
            "UPDATE fontes SET ativa = ?, atualizado_em = ?" + clausula,
            [1 if ativa else 0, self._agora()] + params,
        )
        self.db.commit()

    def remover(self, fonte_id: int) -> None:
        self.db.execute("DELETE FROM fontes WHERE id = ?", (fonte_id,))
        self.db.commit()

    def promover_para_global(self, fonte_id: int) -> None:
        """Torna uma fonte privada parte do catálogo global (empresa_id nulo)."""
        self.db.execute(
            "UPDATE fontes SET empresa_id = NULL, atualizado_em = ? WHERE id = ?",
            (self._agora(), fonte_id),
        )
        self.db.commit()

    def importar(self, itens: list[dict]) -> dict:
        """Importa várias fontes de uma vez, ignorando URLs já cadastradas.

        Retorna um resumo ``{"inseridas": n, "ignoradas": m}``.
        """
        inseridas = ignoradas = 0
        for item in itens:
            url_bruta = item.get("url")
            nome = (item.get("nome") or "").strip()
            if not url_bruta or not nome:
                ignoradas += 1
                continue
            try:
                url = _normalizar_url(url_bruta)
            except ValueError:
                ignoradas += 1
                continue
            if self.existe_url(url):
                ignoradas += 1
                continue
            self.criar(
                nome,
                url,
                categoria=item.get("categoria"),
                regiao=item.get("regiao"),
                idioma=item.get("idioma"),
                relevancia=int(item.get("relevancia", 3) or 3),
                prioridade=int(item.get("prioridade", 3) or 3),
                ativa=bool(item.get("ativa", True)),
            )
            inseridas += 1
        return {"inseridas": inseridas, "ignoradas": ignoradas}

    def semear_se_vazio(self) -> int:
        """Popula o cadastro com as fontes-semente, apenas se estiver vazio.

        Retorna a quantidade de fontes inseridas.
        """
        if self.count() > 0:
            return 0
        # As fontes-semente entram DESATIVADAS por padrão: a ativação é uma
        # decisão explícita (o operador liga o que vai monitorar).
        itens = carregar_seed()
        for it in itens:
            it["ativa"] = False
        resultado = self.importar(itens)
        return resultado["inseridas"]


class CandidataRepository:
    """Curadoria: fontes privadas sugeridas pelas empresas para avaliação.

    Quando uma empresa cadastra uma fonte privada, um registro é guardado aqui
    ('outro local') para a plataforma avaliar se vale promover ao catálogo
    global em novas versões.
    """

    STATUS = ("pendente", "promovida", "descartada")

    def __init__(self, db: Database):
        self.db = db

    def _agora(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def registrar(self, fonte: Fonte) -> None:
        self.db.insert(
            "INSERT INTO fontes_candidatas (fonte_id, empresa_id, nome, url, "
            "categoria, regiao, status, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fonte.id, fonte.empresa_id, fonte.nome, fonte.url,
             fonte.categoria, fonte.regiao, "pendente", self._agora()),
        )
        self.db.commit()

    def listar(self, *, status: Optional[str] = None) -> list[dict]:
        if status:
            return self.db.query_all(
                "SELECT * FROM fontes_candidatas WHERE status = ? "
                "ORDER BY criado_em DESC, id DESC",
                (status,),
            )
        return self.db.query_all(
            "SELECT * FROM fontes_candidatas ORDER BY criado_em DESC, id DESC"
        )

    def get(self, cid: int) -> Optional[dict]:
        return self.db.query_one("SELECT * FROM fontes_candidatas WHERE id = ?", (cid,))

    def definir_status(self, cid: int, status: str) -> None:
        if status not in self.STATUS:
            raise ValueError(f"Status inválido: {status!r}.")
        self.db.execute(
            "UPDATE fontes_candidatas SET status = ? WHERE id = ?", (status, cid)
        )
        self.db.commit()

    def contar_pendentes(self) -> int:
        return int(
            self.db.scalar(
                "SELECT COUNT(*) FROM fontes_candidatas WHERE status = 'pendente'"
            )
            or 0
        )


def _clamp(valor: int, minimo: int = 1, maximo: int = 5) -> int:
    try:
        v = int(valor)
    except (TypeError, ValueError):
        v = 3
    return max(minimo, min(maximo, v))
