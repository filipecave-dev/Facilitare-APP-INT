"""Execução na thread da tela.

O Outlook é controlado por COM, que exige uma thread que atenda as mensagens
do Windows. A thread do disparo passa 3 minutos parada entre os envios sem
atender essas mensagens, e o Outlook derrubava a ligação depois do primeiro
e-mail ("Falha ao criar o e-mail no Outlook"). A tela (tkinter) atende as
mensagens o tempo todo — por isso a pré-visualização sempre funcionou.

``ExecutorPrincipal`` deixa a thread do disparo pedir que uma função rode na
thread da tela e esperar o resultado. A tela chama ``processar_pendentes()``
periodicamente (junto com os eventos do disparo).
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable


class ExecutorPrincipal:
    def __init__(self):
        self.thread_principal = threading.current_thread()
        self._fila: "queue.Queue" = queue.Queue()

    def chamar(self, funcao: Callable, *args, **kwargs) -> Any:
        """Roda ``funcao`` na thread da tela e devolve o resultado (ou levanta
        a mesma exceção). Chamado da própria tela, roda direto."""
        if threading.current_thread() is self.thread_principal:
            return funcao(*args, **kwargs)
        pronto = threading.Event()
        caixa: dict = {}
        self._fila.put((funcao, args, kwargs, pronto, caixa))
        pronto.wait()
        if "erro" in caixa:
            raise caixa["erro"]
        return caixa.get("valor")

    def processar_pendentes(self) -> int:
        """Executa o que a thread do disparo pediu. Retorna quantos rodaram."""
        feitos = 0
        while True:
            try:
                funcao, args, kwargs, pronto, caixa = self._fila.get_nowait()
            except queue.Empty:
                return feitos
            try:
                caixa["valor"] = funcao(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - devolvido a quem pediu
                caixa["erro"] = exc
            finally:
                pronto.set()
                feitos += 1


class EnviadorNaTela:
    """Enviador cujo trabalho roda na thread da tela via ``ExecutorPrincipal``."""

    def __init__(self, executor: ExecutorPrincipal, criar: Callable[[], Any]):
        self.executor = executor
        self.enviador = executor.chamar(criar)

    def enviar(self, email) -> str:
        return self.executor.chamar(self.enviador.enviar, email)
