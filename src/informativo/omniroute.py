"""Integração com o **Omniroute** para captação de informações.

O Omniroute é usado como um gateway de IA **compatível com a API da OpenAI**
(endpoint ``/v1/chat/completions`` com header ``Authorization: Bearer <chave>``).
A URL base, a chave e o modelo são configurados na tela de Configurações e
persistidos em ``configuracoes`` — nada fica fixo no código.

Uso típico::

    cli = client_from_settings(SettingsRepository(db))
    texto = cli.chat("Resuma as novidades de greves na Itália hoje.")

Observação de rede: o app precisa **alcançar** a URL do Omniroute. Se ele
estiver em ``http://localhost:20128`` (na máquina do usuário), só um app
rodando na mesma máquina consegue chamá-lo; um deploy na nuvem (Render) precisa
de uma URL pública (ex.: túnel ngrok/cloudflared).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

# Chaves de configuração persistidas em ``configuracoes``.
CFG_URL = "omniroute_url"
CFG_MODELO = "omniroute_modelo"
CFG_CHAVE = "api_omniroute"


class OmnirouteError(Exception):
    """Falha ao falar com o Omniroute (configuração, rede ou resposta)."""


class OmnirouteClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        modelo: str = "",
        timeout: int = 60,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.modelo = (modelo or "").strip()
        self.timeout = timeout

    def configurado(self) -> bool:
        return bool(self.base_url and self.modelo)

    def _endpoint(self) -> str:
        base = self.base_url
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    def chat(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> str:
        if not self.base_url:
            raise OmnirouteError("URL base do Omniroute não configurada (Configurações).")
        if not self.modelo:
            raise OmnirouteError("Modelo do Omniroute não configurado (Configurações).")

        mensagens = []
        if system:
            mensagens.append({"role": "system", "content": system})
        mensagens.append({"role": "user", "content": prompt})
        corpo = json.dumps({
            "model": self.modelo,
            "messages": mensagens,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(self._endpoint(), data=corpo, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detalhe = exc.read().decode("utf-8", errors="ignore")[:300]
            raise OmnirouteError(f"HTTP {exc.code} do Omniroute: {detalhe}")
        except urllib.error.URLError as exc:
            raise OmnirouteError(
                f"Não consegui conectar ao Omniroute ({self._endpoint()}): {exc.reason}. "
                "Verifique se a URL é acessível a partir de onde o app roda."
            )
        except Exception as exc:  # noqa: BLE001
            raise OmnirouteError(f"Erro inesperado ao chamar o Omniroute: {exc}")

        try:
            return dados["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            raise OmnirouteError(
                "Resposta do Omniroute em formato inesperado: "
                + json.dumps(dados)[:300]
            )


class CaptacaoRepository:
    """Armazena, lista e faz a triagem dos resumos captados por fonte.

    Cada captação tem um ``status``: ``pendente`` (aguardando escolha),
    ``aprovada`` (pode ser utilizada) ou ``descartada``.
    """

    STATUS = ("pendente", "aprovada", "descartada")
    # Três frentes do informativo (mapa mental): classificação editorial.
    FRENTES = ("Alerta", "Informativo", "Notícias de Mercado")

    def __init__(self, db):
        self.db = db

    def registrar(self, fonte, conteudo: str, *, provedor: str = None,
                  empresa_id=None, evitar_repetido: bool = True):
        """Registra uma captação, com prioridade por tema e deduplicação.

        Se ``evitar_repetido`` e o conteúdo repetir uma captação recente (mesma
        empresa) — por assinatura ou alta similaridade —, **não** insere e
        devolve ``None``. Caso contrário devolve o ``id`` inserido.
        """
        from datetime import datetime, timezone

        from .priorizacao import assinatura, e_repetida, prioridade_da_noticia

        regiao = getattr(fonte, "regiao", None)
        if evitar_repetido:
            recentes = self.listar_recentes(
                120, empresa_id=empresa_id, somente_empresa=empresa_id is not None
            )
            if e_repetida(conteudo, recentes):
                return None
        prio = prioridade_da_noticia(conteudo, regiao or "")
        assn = assinatura(conteudo)
        agora = datetime.now(timezone.utc).isoformat()
        novo_id = self.db.insert(
            "INSERT INTO captacoes (fonte_id, fonte_nome, categoria, regiao, "
            "provedor, empresa_id, conteudo, prioridade, assinatura, status, "
            "criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fonte.id, fonte.nome, getattr(fonte, "categoria", None),
             regiao, provedor, empresa_id, conteudo, prio, assn, "pendente", agora),
        )
        self.db.commit()
        return novo_id

    def _filtro_empresa(self, empresa_id, somente_empresa):
        """(clausula, params) para isolar por empresa. Plataforma vê tudo."""
        if not somente_empresa:
            return "", []
        return "empresa_id = ?", [empresa_id]

    def listar_recentes(self, limite: int = 50, *, status: str = None,
                        empresa_id=None, somente_empresa: bool = False) -> list[dict]:
        clausulas, params = [], []
        if status:
            clausulas.append("status = ?")
            params.append(status)
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        if cl:
            clausulas.append(cl)
            params += pa
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        params.append(limite)
        # Ordena por prioridade temática (desastres, greve aérea, aviação/
        # viagens, Brasil) e, dentro do mesmo peso, pelas mais recentes.
        return self.db.query_all(
            "SELECT * FROM captacoes" + where +
            " ORDER BY prioridade DESC, criado_em DESC, id DESC LIMIT ?", params,
        )

    def get(self, captacao_id: int) -> dict:
        return self.db.query_one("SELECT * FROM captacoes WHERE id = ?", (captacao_id,))

    def definir_status(self, captacao_id: int, status: str) -> None:
        if status not in self.STATUS:
            raise ValueError(f"Status inválido: {status!r}.")
        self.db.execute(
            "UPDATE captacoes SET status = ? WHERE id = ?", (status, captacao_id)
        )
        self.db.commit()

    def definir_empresa(self, captacao_id: int, empresa_id) -> None:
        """Define a empresa-destino da captação (para qual cliente vai o
        informativo). ``None`` volta para global/sem empresa."""
        self.db.execute(
            "UPDATE captacoes SET empresa_id = ? WHERE id = ?",
            (empresa_id, captacao_id),
        )
        self.db.commit()

    def atribuir_empresa_em_massa(self, empresa_id, *, status=None,
                                  apenas_sem_empresa: bool = True) -> int:
        """Atribui várias captações a uma empresa. Por padrão só as que ainda
        não têm empresa (``empresa_id IS NULL``). Devolve quantas mudaram."""
        clausulas, params = [], [empresa_id]
        if apenas_sem_empresa:
            clausulas.append("empresa_id IS NULL")
        if status:
            clausulas.append("status = ?")
            params.append(status)
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        n = int(self.db.scalar(
            "SELECT COUNT(*) FROM captacoes" + where,
            params[1:] if params[1:] else [],
        ) or 0)
        self.db.execute(
            "UPDATE captacoes SET empresa_id = ?" + where, params
        )
        self.db.commit()
        return n

    def expurgar_antigas(self, dias: int, *, empresa_id=None,
                         somente_empresa: bool = False) -> int:
        """Remove captações mais antigas que ``dias`` dias (retenção de dados).

        Respeita o escopo de empresa. ``dias <= 0`` não remove nada. Devolve
        quantas foram removidas.
        """
        if not dias or dias <= 0:
            return 0
        from datetime import datetime, timedelta, timezone

        limite = (datetime.now(timezone.utc) - timedelta(days=int(dias))).isoformat()
        clausulas, params = ["criado_em < ?"], [limite]
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        if cl:
            clausulas.append(cl)
            params += pa
        where = " WHERE " + " AND ".join(clausulas)
        n = int(self.db.scalar("SELECT COUNT(*) FROM captacoes" + where, params) or 0)
        self.db.execute("DELETE FROM captacoes" + where, params)
        self.db.commit()
        return n

    def definir_frente(self, captacao_id: int, frente) -> None:
        """Reclassifica a captação em uma das frentes (ou limpa com None)."""
        if frente not in (None, "") and frente not in self.FRENTES:
            raise ValueError(f"Frente inválida: {frente!r}.")
        self.db.execute(
            "UPDATE captacoes SET frente = ? WHERE id = ?",
            (frente or None, captacao_id),
        )
        self.db.commit()

    def definir_parafrase(self, captacao_id: int, texto: str) -> None:
        """Guarda o texto parafraseado pela IA para uso no informativo."""
        self.db.execute(
            "UPDATE captacoes SET parafrase = ? WHERE id = ?",
            (texto, captacao_id),
        )
        self.db.commit()

    def limpar(self, *, status=None, empresa_id=None,
               somente_empresa: bool = False) -> int:
        """Remove captações (opcionalmente só de um status), respeitando escopo.

        Devolve o número de registros removidos. A plataforma (``somente_empresa``
        falso) pode limpar tudo; uma empresa limpa apenas as suas.
        """
        clausulas, params = [], []
        if status:
            clausulas.append("status = ?")
            params.append(status)
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        if cl:
            clausulas.append(cl)
            params += pa
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        n = int(self.db.scalar("SELECT COUNT(*) FROM captacoes" + where, params) or 0)
        self.db.execute("DELETE FROM captacoes" + where, params)
        self.db.commit()
        return n

    def contar_por_status(self, *, empresa_id=None,
                          somente_empresa: bool = False) -> dict:
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        where = (" WHERE " + cl) if cl else ""
        linhas = self.db.query_all(
            "SELECT status, COUNT(*) AS n FROM captacoes" + where +
            " GROUP BY status", pa,
        )
        base = {s: 0 for s in self.STATUS}
        for l in linhas:
            base[l["status"]] = int(l["n"])
        return base

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM captacoes") or 0)

    def definir_disparado(self, captacao_id: int, disparado: bool = True) -> None:
        """Marca (ou desmarca) o comunicado como disparado, com carimbo de data."""
        from datetime import datetime, timezone

        quando = datetime.now(timezone.utc).isoformat() if disparado else None
        self.db.execute(
            "UPDATE captacoes SET disparado_em = ? WHERE id = ?",
            (quando, captacao_id),
        )
        self.db.commit()

    # -- indicadores para o painel -----------------------------------------
    def metricas(self, *, empresa_id=None, somente_empresa: bool = False) -> dict:
        """Contadores e datas para o painel, respeitando o escopo de empresa."""
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        where = (" WHERE " + cl) if cl else ""
        row = self.db.query_one(
            "SELECT COUNT(*) AS captadas, "
            "COALESCE(SUM(CASE WHEN status='aprovada' THEN 1 ELSE 0 END),0) AS aprovadas, "
            "COALESCE(SUM(CASE WHEN status='descartada' THEN 1 ELSE 0 END),0) AS descartadas, "
            "COALESCE(SUM(CASE WHEN status='pendente' THEN 1 ELSE 0 END),0) AS pendentes, "
            "COALESCE(SUM(CASE WHEN parafrase IS NOT NULL AND parafrase <> '' THEN 1 ELSE 0 END),0) AS parafraseadas, "
            "COALESCE(SUM(CASE WHEN disparado_em IS NOT NULL THEN 1 ELSE 0 END),0) AS disparadas, "
            "COUNT(DISTINCT fonte_id) AS fontes_consultadas, "
            "MAX(criado_em) AS ultima_captacao, "
            "MAX(disparado_em) AS ultimo_disparo "
            "FROM captacoes" + where, pa,
        ) or {}
        return {k: (int(v) if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit())
                    else v) for k, v in row.items()}

    def top_fontes(self, limite: int = 8, *, empresa_id=None,
                   somente_empresa: bool = False) -> list[dict]:
        """Fontes mais utilizadas (mais captações), com aproveitamento."""
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        where = (" WHERE " + cl) if cl else ""
        pa = list(pa) + [int(limite)]
        return self.db.query_all(
            "SELECT fonte_nome, COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN status='aprovada' THEN 1 ELSE 0 END),0) AS aprovadas "
            "FROM captacoes" + where +
            " GROUP BY fonte_nome ORDER BY total DESC, fonte_nome ASC LIMIT ?", pa,
        )

    def fontes_sem_relevancia(self, limite: int = 8, *, empresa_id=None,
                              somente_empresa: bool = False) -> list[dict]:
        """Fontes que trouxeram captações mas nenhuma foi aprovada (0 relevância)."""
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        where = (" WHERE " + cl) if cl else ""
        pa = list(pa) + [int(limite)]
        return self.db.query_all(
            "SELECT fonte_nome, COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN status='descartada' THEN 1 ELSE 0 END),0) AS descartadas "
            "FROM captacoes" + where +
            " GROUP BY fonte_nome "
            "HAVING SUM(CASE WHEN status='aprovada' THEN 1 ELSE 0 END) = 0 "
            "ORDER BY total DESC, fonte_nome ASC LIMIT ?", pa,
        )

    def por_frente(self, *, empresa_id=None, somente_empresa: bool = False) -> dict:
        """Distribuição das aprovadas pelas frentes editoriais."""
        clausulas, params = ["status = 'aprovada'"], []
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        if cl:
            clausulas.append(cl)
            params += pa
        where = " WHERE " + " AND ".join(clausulas)
        linhas = self.db.query_all(
            "SELECT frente, COUNT(*) AS n FROM captacoes" + where +
            " GROUP BY frente", params,
        )
        base = {f: 0 for f in self.FRENTES}
        for l in linhas:
            fr = l["frente"] or "Informativo"
            base[fr] = base.get(fr, 0) + int(l["n"])
        return base

    def serie_diaria(self, dias: int = 14, *, empresa_id=None,
                     somente_empresa: bool = False) -> list[dict]:
        """Captações por dia (últimos ``dias`` dias), mais recentes por último."""
        cl, pa = self._filtro_empresa(empresa_id, somente_empresa)
        where = (" WHERE " + cl) if cl else ""
        linhas = self.db.query_all(
            "SELECT substr(criado_em,1,10) AS dia, COUNT(*) AS n "
            "FROM captacoes" + where +
            " GROUP BY substr(criado_em,1,10) ORDER BY dia DESC LIMIT ?",
            list(pa) + [int(dias)],
        )
        return list(reversed(linhas))


def expurgar_por_retencao(db) -> int:
    """Aplica a retenção de cada empresa: remove captações além do prazo.

    Percorre as empresas com ``dias_retencao > 0`` e apaga as captações dela
    mais antigas que esse número de dias. Devolve o total removido. Seguro para
    rodar a cada boot (idempotente).
    """
    from .empresas import EmpresaRepository

    repo_cap = CaptacaoRepository(db)
    total = 0
    for emp in EmpresaRepository(db).listar():
        if emp.dias_retencao and emp.dias_retencao > 0:
            total += repo_cap.expurgar_antigas(
                emp.dias_retencao, empresa_id=emp.id, somente_empresa=True
            )
    return total


def client_from_settings(settings_repo, timeout: int = 60) -> OmnirouteClient:
    """Monta um :class:`OmnirouteClient` a partir das configurações salvas."""
    return OmnirouteClient(
        base_url=settings_repo.get(CFG_URL, "") or "",
        api_key=settings_repo.get(CFG_CHAVE, "") or "",
        modelo=settings_repo.get(CFG_MODELO, "") or "",
        timeout=timeout,
    )


def prompt_para_fonte(fonte, conteudo: str = "", dias: int = 5) -> tuple[str, str]:
    """Monta (system, prompt) para resumir as novidades de uma fonte.

    Se ``conteudo`` (texto coletado da fonte) for fornecido, a IA é instruída a
    se basear **apenas** nele — o que torna o resumo factual e atual. Sem
    conteúdo, cai no modo genérico (conhecimento geral do modelo).
    """
    system = (
        "Você é um analista de viagens corporativas. Resuma, de forma objetiva "
        "e em português do Brasil, as informações mais relevantes para viajantes "
        "(greves, cancelamentos, fechamentos de aeroporto, clima severo, "
        "segurança e saúde). Seja conciso: 3 a 5 tópicos curtos."
    )
    partes = [f"Fonte: {fonte.nome} ({fonte.url})."]
    if getattr(fonte, "categoria", None):
        partes.append(f"Categoria: {fonte.categoria}.")
    if getattr(fonte, "regiao", None):
        partes.append(f"Região/País: {fonte.regiao}.")

    if conteudo:
        from datetime import datetime, timedelta, timezone

        hoje = datetime.now(timezone.utc)
        inicio = (hoje - timedelta(days=dias)).strftime("%d/%m/%Y")
        partes.append(
            f"Hoje é {hoje.strftime('%d/%m/%Y')}. Considere SOMENTE novidades dos "
            f"últimos {dias} dias (a partir de {inicio}). Ignore itens mais antigos "
            "e não invente datas nem fatos. "
            "Baseie-se APENAS no conteúdo recente da fonte abaixo. Liste em 3 a 5 "
            "tópicos os itens relevantes para viajantes; para cada item, inclua o "
            "título/assunto e a data quando houver. Se nada no período for "
            "relevante, responda exatamente: 'Sem itens relevantes nesta captura.'"
            "\n\n=== CONTEÚDO DA FONTE ===\n" + conteudo
        )
    else:
        partes.append(
            "Não foi possível coletar o conteúdo recente desta fonte. Deixe claro "
            "que não há dados coletados e sugira verificar a fonte diretamente."
        )
    return system, "\n".join(partes)


def prompt_parafrase(captacao: dict, *, nome_solucao: str = "") -> tuple[str, str]:
    """Monta (system, prompt) para a IA **parafrasear** um item aprovado.

    A paráfrase reescreve o resumo captado com texto original (sem cópia literal),
    pronto para entrar no informativo. Recebe o dicionário da captação.
    """
    frente = (captacao.get("frente") or "Informativo").strip()
    system = (
        "Você é redator de um informativo de viagens corporativas. Reescreva o "
        "conteúdo recebido com TEXTO ORIGINAL (paráfrase), em português do Brasil, "
        "sem copiar frases literais e sem inventar fatos ou datas. Mantenha o tom "
        f"editorial da frente '{frente}'. Produza um parágrafo curto (2 a 4 frases) "
        "com um título curto na primeira linha, no formato:\nTítulo: <título>\n"
        "<parágrafo>."
    )
    partes = []
    if nome_solucao:
        partes.append(f"Solução/cliente: {nome_solucao}.")
    if captacao.get("fonte_nome"):
        partes.append(f"Fonte: {captacao['fonte_nome']}.")
    if captacao.get("regiao"):
        partes.append(f"Região/País: {captacao['regiao']}.")
    partes.append(f"Frente editorial: {frente}.")
    partes.append("=== CONTEÚDO A PARAFRASEAR ===\n" + (captacao.get("conteudo") or ""))
    return system, "\n".join(partes)
