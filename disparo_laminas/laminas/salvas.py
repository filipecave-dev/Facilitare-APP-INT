"""Campanhas salvas: combinações prontas de lâmina, apresentação e texto.

Cada campanha salva tem um nome escolhido pelo usuário e guarda:

- ``pasta``    — subpasta de lâminas (CORPORATIVO, EVENTOS...);
- ``laminas``  — caminhos completos das lâminas selecionadas;
- ``alternar`` — se as lâminas são mescladas em rodízio;
- ``anexo``    — nome do arquivo de apresentação ("" = sem anexo);
- ``mensagem`` — assunto, texto de cima e texto de baixo.

Ficam no ``config.json`` (pasta de dados), em ``campanhas_salvas``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

CHAVE = "campanhas_salvas"
TAMANHO_MAXIMO_NOME = 60
CAMPOS = ("pasta", "laminas", "alternar", "anexo", "mensagem")


class NomeInvalido(ValueError):
    pass


def normalizar_nome(nome: str) -> str:
    nome = " ".join((nome or "").split())
    if not nome:
        raise NomeInvalido("Informe um nome para a campanha.")
    if len(nome) > TAMANHO_MAXIMO_NOME:
        raise NomeInvalido(f"Use no máximo {TAMANHO_MAXIMO_NOME} caracteres no nome.")
    if nome.startswith("("):
        raise NomeInvalido("O nome não pode começar com parênteses.")
    return nome


def listar(cfg: dict) -> list[str]:
    return sorted((cfg.get(CHAVE) or {}).keys(), key=str.casefold)


def obter(cfg: dict, nome: str) -> Optional[dict]:
    return (cfg.get(CHAVE) or {}).get(nome)


def existente(cfg: dict, nome: str) -> Optional[str]:
    """Nome já salvo que é igual a ``nome`` ignorando maiúsculas/minúsculas."""
    alvo = nome.casefold()
    return next((n for n in listar(cfg) if n.casefold() == alvo), None)


def salvar(cfg: dict, nome: str, dados: dict) -> str:
    """Grava a campanha (substitui a de mesmo nome). Retorna o nome usado."""
    nome = normalizar_nome(nome)
    nome = existente(cfg, nome) or nome
    registro = {campo: dados.get(campo) for campo in CAMPOS}
    registro["laminas"] = [str(p) for p in (dados.get("laminas") or [])]
    registro["alternar"] = bool(dados.get("alternar"))
    registro["anexo"] = dados.get("anexo") or ""
    registro["mensagem"] = dict(dados.get("mensagem") or {})
    registro["atualizada_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg.setdefault(CHAVE, {})[nome] = registro
    return nome


def excluir(cfg: dict, nome: str) -> None:
    (cfg.get(CHAVE) or {}).pop(nome, None)


def mesmo_conteudo(salva: Optional[dict], atual: dict) -> bool:
    """Compara o que está na tela com a campanha salva (ignora a data)."""
    if not salva:
        return False
    return all(_comparavel(campo, salva.get(campo)) == _comparavel(campo, atual.get(campo))
               for campo in CAMPOS)


def _comparavel(campo: str, valor):
    if campo == "laminas":
        return [str(p) for p in (valor or [])]
    if campo == "alternar":
        return bool(valor)
    if campo == "anexo":
        return valor or ""
    if campo == "mensagem":
        valor = valor or {}
        return {k: valor.get(k, "") for k in ("assunto", "texto_inicio", "texto_fim")}
    return valor or ""


def localizar_laminas(salva: dict, disponiveis: list[Path]) -> tuple[list[Path], list[str]]:
    """Lâminas da campanha salva: pelo caminho completo ou, se a pasta mudou
    de lugar, pelo nome do arquivo entre as ``disponiveis``. Retorna
    ``(encontradas, nomes_que_faltam)``."""
    encontradas: list[Path] = []
    faltando: list[str] = []
    for caminho in salva.get("laminas") or []:
        p = Path(caminho)
        mesmo_nome = next((d for d in disponiveis if d.name == p.name), None)
        if p in disponiveis or p.is_file():
            encontradas.append(p)
        elif mesmo_nome is not None:
            encontradas.append(mesmo_nome)
        else:
            faltando.append(p.name)
    return encontradas, faltando
