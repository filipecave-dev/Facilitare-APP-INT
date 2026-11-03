"""Motor do disparo: envia em segundo plano respeitando limite e intervalo.

Regras:

- no máximo ``limite_diario`` envios com status *Enviado* por dia (conta
  também o que já foi enviado mais cedo no mesmo dia);
- ``intervalo_seg`` entre um envio e o próximo (o primeiro sai na hora);
- antes de cada envio o histórico é consultado de novo: um e-mail que já
  recebeu lâmina é pulado, a não ser que o reenvio tenha sido autorizado;
- cada tentativa (Enviado ou Erro) é registrada no histórico.

A tela acompanha o andamento pelos eventos colocados em ``eventos`` (uma
``queue.Queue``) no formato ``(tipo, dados)``.
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .base import Contato
from .campanhas import lamina_do_envio
from .envio import descrever_erro
from .historico import ENVIADO, ERRO, Historico
from .mensagem import Email, montar

# Para o disparo depois de tantos erros seguidos (problema no Outlook ou nos
# arquivos): evita marcar a lista inteira como erro, 3 minutos por vez.
MAX_ERROS_SEGUIDOS = 3


class Disparo(threading.Thread):
    def __init__(self, contatos: list[Contato], *, historico: Historico,
                 criar_enviador: Callable[[], object], mensagem: dict, campanha: str,
                 laminas: list[Path], alternar_laminas: bool, email_copia: str,
                 copia_oculta: str, limite_diario: int, intervalo_seg: float,
                 eventos: "queue.Queue", anexos: Optional[list[Path]] = None,
                 remetente: str = "", agora: Callable[[], datetime] = datetime.now,
                 relogio: Callable[[], float] = time.monotonic):
        super().__init__(daemon=True, name="disparo-laminas")
        self.contatos = list(contatos)
        self.historico = historico
        self.criar_enviador = criar_enviador
        self.mensagem = mensagem
        self.campanha = campanha
        self.laminas = list(laminas)
        self.alternar_laminas = alternar_laminas
        self.anexos = list(anexos or [])
        self.remetente = remetente
        self.email_copia = email_copia
        self.copia_oculta = copia_oculta
        self.limite_diario = int(limite_diario)
        self.intervalo_seg = float(intervalo_seg)
        self.eventos = eventos
        self.agora = agora
        self.relogio = relogio
        self._parar = threading.Event()

    def parar(self) -> None:
        self._parar.set()

    @property
    def parando(self) -> bool:
        return self._parar.is_set()

    def _emitir(self, tipo: str, **dados) -> None:
        self.eventos.put((tipo, dados))

    def montar_email(self, contato: Contato, indice: int) -> Email:
        return montar(contato, self.mensagem,
                      imagem=lamina_do_envio(self.laminas, indice, self.alternar_laminas),
                      cc=self.email_copia, cco=self.copia_oculta, anexos=self.anexos,
                      agora=self.agora())

    def run(self) -> None:
        try:
            enviador = self.criar_enviador()
        except Exception as exc:  # noqa: BLE001 - mostrado na tela
            self._emitir("fim", motivo=str(exc), enviados=0, erros=0)
            return

        enviados = erros = tentativas = erros_seguidos = 0
        ultimo: Optional[float] = None
        motivo = "Disparo concluído."
        for contato in self.contatos:
            if self._parar.is_set():
                motivo = "Disparo interrompido pelo usuário."
                break

            if self.historico.enviados_no_dia(self.agora().date()) >= self.limite_diario:
                motivo = (f"Limite diário de {self.limite_diario} envios atingido. "
                          "Os contatos restantes continuam pendentes para o próximo dia.")
                break

            if not contato.forcar and self.historico.data_envio(contato.email) is not None:
                self._emitir("pulado", contato=contato, motivo="Já enviado (histórico)")
                continue

            if ultimo is not None:
                espera = ultimo + self.intervalo_seg - self.relogio()
                if espera > 0:
                    self._emitir("aguardando", contato=contato, segundos=espera)
                    if self._parar.wait(espera):
                        motivo = "Disparo interrompido pelo usuário."
                        break

            email = self.montar_email(contato, tentativas)
            tentativas += 1
            ultimo = self.relogio()
            self._emitir("enviando", contato=contato)
            registro = dict(email=contato.email, nome=contato.nome, empresa=contato.empresa,
                            cc=email.cc, campanha=self.campanha,
                            lamina=email.imagem.name if email.imagem else "",
                            anexo=", ".join(a.name for a in email.anexos),
                            remetente=self.remetente,
                            assunto=email.assunto,
                            data_hora=self.agora().strftime("%Y-%m-%d %H:%M:%S"))
            try:
                obs = enviador.enviar(email) or ""
            except Exception as exc:  # noqa: BLE001 - registrado e mostrado na tela
                erros += 1
                erros_seguidos += 1
                texto = descrever_erro(exc)
                self.historico.registrar(**registro, status=ERRO, erro=texto)
                self._emitir("erro", contato=contato, erro=texto)
                if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                    motivo = (f"Disparo interrompido após {erros_seguidos} erros seguidos. "
                              f"Último erro: {texto}")
                    break
                continue
            erros_seguidos = 0
            enviados += 1
            self.historico.registrar(**registro, status=ENVIADO, erro=obs)
            self._emitir("enviado", contato=contato, email=email, obs=obs,
                         hoje=self.historico.enviados_no_dia(self.agora().date()))

        self._emitir("fim", motivo=motivo, enviados=enviados, erros=erros)
