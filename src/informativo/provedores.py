"""Provedores de IA (conexões) usados para captar informações.

Cada provedor é uma conexão a um modelo de IA — via **OmniRoute** ou direto
(GPT, DeepSeek, Gemini, Claude...). Um provedor pode ser **global** (do sistema,
``empresa_id`` nulo) ou pertencer a **uma empresa/cliente**, que assim usa a
**sua própria chave**.

Dois formatos de requisição são suportados:

* ``openai``    — endpoint ``/v1/chat/completions`` (OmniRoute, GPT, DeepSeek,
  Gemini via endpoint OpenAI-compatible, Groq, Mistral...).
* ``anthropic`` — endpoint ``/v1/messages`` da API da Anthropic (Claude direto),
  com headers ``x-api-key`` e ``anthropic-version``.

O acesso é feito por HTTP direto (biblioteca padrão), mantendo o app leve e o
tratamento uniforme entre provedores.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .db import Database

FORMATOS = ("openai", "anthropic")
ANTHROPIC_VERSION = "2023-06-01"


class IAError(Exception):
    """Falha ao falar com um provedor de IA (configuração, rede ou resposta)."""


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class ClienteIA:
    def __init__(
        self,
        formato: str,
        base_url: str,
        modelo: str,
        api_key: str = "",
        timeout: int = 60,
    ):
        self.formato = (formato or "openai").strip().lower()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.modelo = (modelo or "").strip()
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def configurado(self) -> bool:
        return bool(self.base_url and self.modelo)

    # Códigos que indicam sobrecarga temporária (vale a pena tentar de novo).
    _TRANSIENTES = {429, 500, 502, 503, 504}

    def _post(self, url: str, headers: dict, corpo: dict,
              tentativas: int = 3) -> dict:
        import time

        dados = json.dumps(corpo).encode("utf-8")
        ultimo_erro = None
        for i in range(tentativas):
            req = urllib.request.Request(url, data=dados, method="POST")
            req.add_header("Content-Type", "application/json")
            for chave, valor in headers.items():
                req.add_header(chave, valor)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detalhe = exc.read().decode("utf-8", errors="ignore")[:300]
                ultimo_erro = IAError(f"HTTP {exc.code}: {detalhe}")
                if exc.code in self._TRANSIENTES and i < tentativas - 1:
                    time.sleep(2 * (i + 1))  # 2s, 4s
                    continue
                raise ultimo_erro
            except urllib.error.URLError as exc:
                ultimo_erro = IAError(
                    f"Não consegui conectar a {url}: {exc.reason}. "
                    "Verifique se a URL é acessível de onde o app roda."
                )
                if i < tentativas - 1:
                    time.sleep(2 * (i + 1))
                    continue
                raise ultimo_erro
            except Exception as exc:  # noqa: BLE001
                raise IAError(f"Erro inesperado: {exc}")
        raise ultimo_erro  # pragma: no cover

    def chat(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 600,
    ) -> str:
        if not self.base_url:
            raise IAError("URL base do provedor não configurada.")
        if not self.modelo:
            raise IAError("Modelo do provedor não configurado.")
        if self.formato == "anthropic":
            return self._chat_anthropic(prompt, system, temperature, max_tokens)
        return self._chat_openai(prompt, system, temperature, max_tokens)

    def _endpoint_openai(self) -> str:
        base = self.base_url
        # Usuário pode colar a URL completa do chat/completions.
        if "/chat/completions" in base:
            return base
        # Raízes de API que já incluem a versão/segmento (ex.: Gemini termina
        # em '/v1beta/openai', OpenAI/DeepSeek em '/v1') recebem só o sufixo.
        if base.endswith(("/openai", "/v1", "/v1beta", "/compat", "/api/v1")):
            return base + "/chat/completions"
        # Host "cru" (ex.: OmniRoute http://localhost:20128).
        return base + "/v1/chat/completions"

    def _chat_openai(self, prompt, system, temperature, max_tokens) -> str:
        mensagens = []
        if system:
            mensagens.append({"role": "system", "content": system})
        mensagens.append({"role": "user", "content": prompt})
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        dados = self._post(self._endpoint_openai(), headers, {
            "model": self.modelo,
            "messages": mensagens,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        try:
            return dados["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            raise IAError("Resposta inesperada: " + json.dumps(dados)[:300])

    def _endpoint_anthropic(self) -> str:
        base = self.base_url or "https://api.anthropic.com"
        if base.endswith("/v1/messages"):
            return base
        if base.endswith("/v1"):
            return base + "/messages"
        return base + "/v1/messages"

    def _chat_anthropic(self, prompt, system, temperature, max_tokens) -> str:
        headers = {"anthropic-version": ANTHROPIC_VERSION}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        corpo = {
            "model": self.modelo,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            corpo["system"] = system
        dados = self._post(self._endpoint_anthropic(), headers, corpo)
        try:
            partes = [b.get("text", "") for b in dados["content"] if b.get("type") == "text"]
            return "".join(partes).strip() or json.dumps(dados)[:300]
        except (KeyError, TypeError):
            raise IAError("Resposta inesperada: " + json.dumps(dados)[:300])


# ---------------------------------------------------------------------------
# Modelo e repositório
# ---------------------------------------------------------------------------
@dataclass
class Provedor:
    id: int
    nome: str
    formato: str
    base_url: str
    modelo: str
    api_key: Optional[str] = None
    empresa_id: Optional[int] = None
    ativo: bool = True
    criado_em: Optional[str] = None

    def cliente(self, timeout: int = 60) -> ClienteIA:
        return ClienteIA(
            self.formato, self.base_url, self.modelo, self.api_key or "", timeout
        )


def _row(r: dict) -> Provedor:
    return Provedor(
        id=r["id"],
        nome=r["nome"],
        formato=r["formato"],
        base_url=r["base_url"],
        modelo=r["modelo"],
        api_key=r.get("api_key"),
        empresa_id=r.get("empresa_id"),
        ativo=bool(r.get("ativo", 1)),
        criado_em=r.get("criado_em"),
    )


class ProvedorRepository:
    def __init__(self, db: Database):
        self.db = db

    def _agora(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM provedores_ia") or 0)

    def get(self, pid: int) -> Optional[Provedor]:
        r = self.db.query_one("SELECT * FROM provedores_ia WHERE id = ?", (pid,))
        return _row(r) if r else None

    def listar(self, *, empresa_id: Optional[int] = None,
               apenas_ativos: bool = False) -> list[Provedor]:
        clausulas, params = [], []
        if empresa_id is not None:
            clausulas.append("empresa_id = ?")
            params.append(empresa_id)
        if apenas_ativos:
            clausulas.append("ativo = 1")
        where = (" WHERE " + " AND ".join(clausulas)) if clausulas else ""
        rows = self.db.query_all(
            "SELECT * FROM provedores_ia" + where + " ORDER BY LOWER(nome) ASC", params
        )
        return [_row(r) for r in rows]

    def criar(self, nome: str, formato: str, base_url: str, modelo: str, *,
              api_key: Optional[str] = None, empresa_id: Optional[int] = None,
              ativo: bool = True) -> Provedor:
        nome = (nome or "").strip()
        formato = (formato or "openai").strip().lower()
        base_url = (base_url or "").strip()
        modelo = (modelo or "").strip()
        if not nome:
            raise ValueError("O nome do provedor é obrigatório.")
        if formato not in FORMATOS:
            raise ValueError(f"Formato inválido: {formato!r}.")
        if not base_url or not modelo:
            raise ValueError("URL base e modelo são obrigatórios.")
        novo_id = self.db.insert(
            "INSERT INTO provedores_ia (nome, formato, base_url, modelo, api_key, "
            "empresa_id, ativo, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nome, formato, base_url, modelo, api_key, empresa_id,
             1 if ativo else 0, self._agora()),
        )
        self.db.commit()
        p = self.get(novo_id)
        assert p is not None
        return p

    def atualizar(self, pid: int, **campos) -> None:
        """Atualiza um provedor. ``api_key`` só é alterada se vier preenchida
        (deixe em branco para manter a chave atual)."""
        permitidos = {"nome", "formato", "base_url", "modelo",
                      "api_key", "empresa_id", "ativo"}
        if self.get(pid) is None:
            raise ValueError("Provedor não encontrado.")
        if "formato" in campos and campos["formato"] not in FORMATOS:
            raise ValueError(f"Formato inválido: {campos['formato']!r}.")
        sets, params = [], []
        for chave, valor in campos.items():
            if chave not in permitidos:
                continue
            if chave == "ativo":
                valor = 1 if valor else 0
            if isinstance(valor, str):
                valor = valor.strip()
            sets.append(f"{chave} = ?")
            params.append(valor)
        if not sets:
            return
        params.append(pid)
        self.db.execute(
            f"UPDATE provedores_ia SET {', '.join(sets)} WHERE id = ?", params
        )
        self.db.commit()

    def alternar_ativo(self, pid: int) -> None:
        self.db.execute(
            "UPDATE provedores_ia SET ativo = 1 - ativo WHERE id = ?", (pid,)
        )
        self.db.commit()

    def remover(self, pid: int) -> None:
        self.db.execute("DELETE FROM provedores_ia WHERE id = ?", (pid,))
        self.db.commit()
