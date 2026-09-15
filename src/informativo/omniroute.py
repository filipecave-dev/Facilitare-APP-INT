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

    def __init__(self, db):
        self.db = db

    def registrar(self, fonte, conteudo: str, *, provedor: str = None):
        from datetime import datetime, timezone

        agora = datetime.now(timezone.utc).isoformat()
        self.db.insert(
            "INSERT INTO captacoes (fonte_id, fonte_nome, categoria, regiao, "
            "provedor, conteudo, status, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fonte.id, fonte.nome, getattr(fonte, "categoria", None),
             getattr(fonte, "regiao", None), provedor, conteudo, "pendente", agora),
        )
        self.db.commit()

    def listar_recentes(self, limite: int = 50, *, status: str = None) -> list[dict]:
        if status:
            return self.db.query_all(
                "SELECT * FROM captacoes WHERE status = ? "
                "ORDER BY criado_em DESC, id DESC LIMIT ?",
                (status, limite),
            )
        return self.db.query_all(
            "SELECT * FROM captacoes ORDER BY criado_em DESC, id DESC LIMIT ?",
            (limite,),
        )

    def definir_status(self, captacao_id: int, status: str) -> None:
        if status not in self.STATUS:
            raise ValueError(f"Status inválido: {status!r}.")
        self.db.execute(
            "UPDATE captacoes SET status = ? WHERE id = ?", (status, captacao_id)
        )
        self.db.commit()

    def contar_por_status(self) -> dict:
        linhas = self.db.query_all(
            "SELECT status, COUNT(*) AS n FROM captacoes GROUP BY status"
        )
        base = {s: 0 for s in self.STATUS}
        for l in linhas:
            base[l["status"]] = int(l["n"])
        return base

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM captacoes") or 0)


def client_from_settings(settings_repo, timeout: int = 60) -> OmnirouteClient:
    """Monta um :class:`OmnirouteClient` a partir das configurações salvas."""
    return OmnirouteClient(
        base_url=settings_repo.get(CFG_URL, "") or "",
        api_key=settings_repo.get(CFG_CHAVE, "") or "",
        modelo=settings_repo.get(CFG_MODELO, "") or "",
        timeout=timeout,
    )


def prompt_para_fonte(fonte, conteudo: str = "") -> tuple[str, str]:
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
        partes.append(
            "Baseie-se APENAS no conteúdo recente da fonte abaixo. Liste em 3 a 5 "
            "tópicos os itens relevantes para viajantes; para cada item, inclua o "
            "título/assunto. Ignore o que não for pertinente. Se nada no conteúdo "
            "for relevante, responda exatamente: 'Sem itens relevantes nesta captura.'"
            "\n\n=== CONTEÚDO DA FONTE ===\n" + conteudo
        )
    else:
        partes.append(
            "Não foi possível coletar o conteúdo recente desta fonte. Deixe claro "
            "que não há dados coletados e sugira verificar a fonte diretamente."
        )
    return system, "\n".join(partes)
