"""Contabilidade de uso e custo das chamadas de IA, com teto diário.

Cada chamada à IA (captura ou paráfrase) registra os tokens de entrada/saída e
um custo estimado, calculado a partir dos preços por 1 milhão de tokens
configurados em Configurações. Um **limite diário** (valor máximo por dia,
editável) permite travar a operação para não estourar o orçamento — útil,
por exemplo, enquanto se testa com a conta gratuita do Gemini.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .db import Database
from .settings_repo import SettingsRepository

# Chaves de configuração (globais da plataforma).
CFG_PRECO_IN = "ia_preco_entrada_mtok"   # preço por 1M tokens de entrada
CFG_PRECO_OUT = "ia_preco_saida_mtok"    # preço por 1M tokens de saída
CFG_MOEDA = "ia_moeda"                    # rótulo da moeda (ex.: US$, R$)
CFG_LIMITE_DIA = "ia_limite_diario"       # teto de custo por dia (0 = sem limite)

# Padrões pensados para o Gemini 2.5 Flash-Lite (confira a tarifa vigente).
PADRAO_PRECO_IN = "0.10"
PADRAO_PRECO_OUT = "0.40"
PADRAO_MOEDA = "US$"
PADRAO_LIMITE_DIA = "1.00"


def _hoje() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _float(valor, padrao: float = 0.0) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


class Precos:
    """Preços e limite atuais, lidos das configurações."""

    def __init__(self, settings: SettingsRepository):
        self.preco_in = _float(settings.get(CFG_PRECO_IN, PADRAO_PRECO_IN))
        self.preco_out = _float(settings.get(CFG_PRECO_OUT, PADRAO_PRECO_OUT))
        self.moeda = settings.get(CFG_MOEDA, PADRAO_MOEDA) or PADRAO_MOEDA
        self.limite_diario = _float(settings.get(CFG_LIMITE_DIA, PADRAO_LIMITE_DIA))

    def custo(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in / 1_000_000) * self.preco_in + \
               (tokens_out / 1_000_000) * self.preco_out


class UsoRepository:
    """Registra e consulta o uso/custo de IA."""

    def __init__(self, db: Database):
        self.db = db

    def registrar(self, operacao: str, uso: dict, custo: float, *,
                  empresa_id=None, provedor: str = None,
                  fonte_id=None, fonte_nome: str = None) -> None:
        self.db.insert(
            "INSERT INTO uso_ia (dia, empresa_id, provedor, operacao, fonte_id, "
            "fonte_nome, tokens_in, tokens_out, custo, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_hoje(), empresa_id, provedor, operacao, fonte_id, fonte_nome,
             int(uso.get("in", 0)), int(uso.get("out", 0)), float(custo),
             datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()

    def curva_abc(self, *, empresa_id=None, somente_empresa: bool = False,
                  limiar_a: float = 0.80, limiar_b: float = 0.95) -> dict:
        """Curva ABC do consumo de tokens **por fonte** (análise de Pareto).

        Ordena as fontes pelo total de tokens (entrada+saída), calcula o
        percentual e o acumulado, e classifica:

        * **A** — fontes que somam até ``limiar_a`` (≈80%) do consumo;
        * **B** — as seguintes até ``limiar_b`` (≈95%);
        * **C** — a cauda restante.

        Devolve ``{"itens": [...], "totais": {...}, "classes": {...}}``.
        """
        clausulas, params = ["fonte_nome IS NOT NULL"], []
        if somente_empresa:
            clausulas.append("empresa_id = ?")
            params.append(empresa_id)
        where = " WHERE " + " AND ".join(clausulas)
        linhas = self.db.query_all(
            "SELECT fonte_nome, COUNT(*) AS chamadas, "
            "COALESCE(SUM(tokens_in),0) AS tokens_in, "
            "COALESCE(SUM(tokens_out),0) AS tokens_out, "
            "COALESCE(SUM(tokens_in + tokens_out),0) AS tokens, "
            "COALESCE(SUM(custo),0) AS custo FROM uso_ia" + where +
            " GROUP BY fonte_nome ORDER BY tokens DESC, fonte_nome ASC", params,
        )
        total_tokens = sum(int(l["tokens"]) for l in linhas) or 0
        total_custo = sum(float(l["custo"]) for l in linhas)
        itens, acumulado = [], 0
        classes = {"A": {"fontes": 0, "tokens": 0, "custo": 0.0},
                   "B": {"fontes": 0, "tokens": 0, "custo": 0.0},
                   "C": {"fontes": 0, "tokens": 0, "custo": 0.0}}
        for l in linhas:
            tk = int(l["tokens"])
            pct = (tk / total_tokens) if total_tokens else 0.0
            # A classe é decidida pelo acumulado ANTES deste item: assim o item
            # que cruza o limiar entra na classe em que começou (o 1º é sempre A,
            # mesmo quando sozinho já passa de 80%).
            if acumulado < limiar_a:
                classe = "A"
            elif acumulado < limiar_b:
                classe = "B"
            else:
                classe = "C"
            acumulado += pct
            itens.append({
                "fonte_nome": l["fonte_nome"],
                "chamadas": int(l["chamadas"]),
                "tokens": tk,
                "custo": float(l["custo"]),
                "pct": pct,
                "pct_acumulado": min(acumulado, 1.0),
                "classe": classe,
            })
            classes[classe]["fontes"] += 1
            classes[classe]["tokens"] += tk
            classes[classe]["custo"] += float(l["custo"])
        return {
            "itens": itens,
            "totais": {"tokens": total_tokens, "custo": total_custo,
                       "fontes": len(itens)},
            "classes": classes,
        }

    def total_do_dia(self, dia: str = None, *, empresa_id=None,
                     somente_empresa: bool = False) -> dict:
        dia = dia or _hoje()
        clausulas, params = ["dia = ?"], [dia]
        if somente_empresa:
            clausulas.append("empresa_id = ?")
            params.append(empresa_id)
        where = " WHERE " + " AND ".join(clausulas)
        row = self.db.query_one(
            "SELECT COUNT(*) AS chamadas, "
            "COALESCE(SUM(tokens_in),0) AS tin, "
            "COALESCE(SUM(tokens_out),0) AS tout, "
            "COALESCE(SUM(custo),0) AS custo FROM uso_ia" + where, params,
        ) or {}
        return {
            "chamadas": int(row.get("chamadas") or 0),
            "tokens_in": int(row.get("tin") or 0),
            "tokens_out": int(row.get("tout") or 0),
            "custo": float(row.get("custo") or 0.0),
        }

    def historico(self, dias: int = 30, *, empresa_id=None,
                  somente_empresa: bool = False) -> list[dict]:
        """Totais por dia (mais recentes primeiro), últimos ``dias`` dias."""
        clausulas, params = [], []
        if somente_empresa:
            clausulas.append("empresa_id = ?")
            params.append(empresa_id)
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        params.append(int(dias))
        return self.db.query_all(
            "SELECT dia, COUNT(*) AS chamadas, "
            "COALESCE(SUM(tokens_in),0) AS tokens_in, "
            "COALESCE(SUM(tokens_out),0) AS tokens_out, "
            "COALESCE(SUM(custo),0) AS custo FROM uso_ia" + where +
            " GROUP BY dia ORDER BY dia DESC LIMIT ?", params,
        )

    def por_operacao(self, dias: int = 30, *, empresa_id=None,
                     somente_empresa: bool = False) -> list[dict]:
        """Totais agregados por operação (captura/parafrase) no período."""
        clausulas, params = [], []
        if somente_empresa:
            clausulas.append("empresa_id = ?")
            params.append(empresa_id)
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        return self.db.query_all(
            "SELECT operacao, COUNT(*) AS chamadas, "
            "COALESCE(SUM(tokens_in),0) AS tokens_in, "
            "COALESCE(SUM(tokens_out),0) AS tokens_out, "
            "COALESCE(SUM(custo),0) AS custo FROM uso_ia" + where +
            " GROUP BY operacao ORDER BY custo DESC", params,
        )

    def resumo_do_dia(self, precos: Precos, *, empresa_id=None,
                      somente_empresa: bool = False) -> dict:
        """Total do dia + situação frente ao limite diário configurado."""
        tot = self.total_do_dia(empresa_id=empresa_id, somente_empresa=somente_empresa)
        limite = precos.limite_diario
        resta = (limite - tot["custo"]) if limite > 0 else None
        return {
            **tot,
            "moeda": precos.moeda,
            "limite": limite,
            "resta": resta,
            "atingido": bool(limite > 0 and tot["custo"] >= limite),
        }


def excede_limite(uso_repo: UsoRepository, precos: Precos, *,
                  empresa_id=None, somente_empresa: bool = False) -> bool:
    """True se o custo de hoje já atingiu/ultrapassou o limite diário."""
    if precos.limite_diario <= 0:
        return False
    tot = uso_repo.total_do_dia(empresa_id=empresa_id, somente_empresa=somente_empresa)
    return tot["custo"] >= precos.limite_diario
