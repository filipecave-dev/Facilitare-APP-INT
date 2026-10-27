"""Envio pelo Outlook instalado no PC (ou simulação em arquivos HTML).

O Outlook é controlado via COM (``pywin32``), como a macro fazia: o e-mail
sai pela conta do Outlook e fica nos Itens Enviados. A lâmina vai embutida no
corpo (anexo com Content-ID), sem aparecer como anexo solto.
"""

from __future__ import annotations

import shutil
import sys
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from .mensagem import Email, corpo_html, documento_html, inserir_no_inicio_do_body

_PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
_PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
_DISPID_SEND_USING_ACCOUNT = 64209


class ErroEnvio(Exception):
    pass


class EnviadorOutlook:
    """Cria e envia e-mails pelo Outlook. Deve ser criado na thread que vai
    usá-lo (o COM é inicializado por thread)."""

    def __init__(self, conta: str = "", incluir_assinatura: bool = True, largura_max: int = 560):
        if sys.platform != "win32":
            raise ErroEnvio("O envio pelo Outlook só funciona no Windows. "
                            "Ative o modo simulação nas Configurações para testar.")
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise ErroEnvio("Pacote pywin32 não instalado. Rode instalar.bat.") from exc
        pythoncom.CoInitialize()
        try:
            self.app = win32com.client.Dispatch("Outlook.Application")
        except Exception as exc:  # noqa: BLE001 - erro COM com mensagem própria
            raise ErroEnvio(f"Não foi possível abrir o Outlook: {exc}") from exc
        self.conta = self._localizar_conta(conta) if conta else None
        self.incluir_assinatura = incluir_assinatura
        self.largura_max = largura_max

    def _localizar_conta(self, endereco: str):
        contas = self.app.Session.Accounts
        disponiveis = []
        for i in range(1, contas.Count + 1):
            conta = contas.Item(i)
            smtp = str(conta.SmtpAddress or "")
            disponiveis.append(smtp)
            if smtp.lower() == endereco.strip().lower():
                return conta
        raise ErroEnvio(f"Conta '{endereco}' não encontrada no Outlook. "
                        f"Contas disponíveis: {', '.join(disponiveis) or 'nenhuma'}")

    def _criar(self, email: Email):
        mail = self.app.CreateItem(0)
        if self.conta is not None:
            try:
                mail.SendUsingAccount = self.conta
            except Exception:  # noqa: BLE001 - contorno conhecido do pywin32
                mail._oleobj_.Invoke(_DISPID_SEND_USING_ACCOUNT, 0, 8, 0, self.conta)
        mail.To = email.para
        mail.CC = email.cc
        mail.BCC = email.cco
        mail.Subject = email.assunto

        src = None
        if email.imagem:
            if not Path(email.imagem).is_file():
                raise ErroEnvio(f"Lâmina não encontrada: {email.imagem}")
            anexo = mail.Attachments.Add(str(Path(email.imagem).resolve()))
            cid = f"lamina-{uuid.uuid4().hex[:12]}"
            anexo.PropertyAccessor.SetProperty(_PR_ATTACH_CONTENT_ID, cid)
            try:
                anexo.PropertyAccessor.SetProperty(_PR_ATTACHMENT_HIDDEN, True)
            except Exception:  # noqa: BLE001 - só estético
                pass
            src = f"cid:{cid}"

        for caminho in email.anexos:
            if not Path(caminho).is_file():
                raise ErroEnvio(f"Anexo não encontrado: {caminho}")
            mail.Attachments.Add(str(Path(caminho).resolve()))

        fragmento = corpo_html(email, src, self.largura_max)
        if self.incluir_assinatura:
            mail.GetInspector  # carrega a assinatura padrão no corpo
            mail.HTMLBody = inserir_no_inicio_do_body(mail.HTMLBody or "", fragmento)
        else:
            mail.HTMLBody = documento_html(fragmento)
        return mail

    def enviar(self, email: Email) -> None:
        self._criar(email).Send()

    def exibir(self, email: Email) -> None:
        """Abre o e-mail pronto no Outlook, sem enviar (pré-visualização)."""
        self._criar(email).Display()


class EnviadorSimulacao:
    """Não envia nada: grava cada e-mail como HTML na pasta ``simulacao``."""

    def __init__(self, pasta: Path, largura_max: int = 560):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.largura_max = largura_max

    def _gravar(self, email: Email) -> Path:
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        nome_seguro = "".join(ch if ch.isalnum() else "_" for ch in email.para)[:60]
        destino = self.pasta / f"{carimbo}_{nome_seguro}.html"
        src = None
        if email.imagem and Path(email.imagem).is_file():
            copia = self.pasta / Path(email.imagem).name
            if not copia.exists():
                shutil.copyfile(email.imagem, copia)
            src = copia.name
        cabecalho = (
            f"<p style='font-family:monospace;background:#eef;padding:8px'>"
            f"Para: {email.para}<br>CC: {email.cc}<br>CCO: {email.cco}<br>"
            f"Assunto: {email.assunto}<br>"
            f"Anexos: {', '.join(Path(a).name for a in email.anexos) or '(nenhum)'}</p><hr>"
        )
        destino.write_text(documento_html(cabecalho + corpo_html(email, src, self.largura_max)),
                           encoding="utf-8")
        return destino

    def enviar(self, email: Email) -> None:
        self._gravar(email)

    def exibir(self, email: Email) -> None:
        webbrowser.open(Path(self._gravar(email)).resolve().as_uri())


def criar_enviador(cfg: dict, pasta_simulacao: Path):
    largura = int(cfg.get("largura_imagem_px") or 560)
    if cfg.get("modo_simulacao"):
        return EnviadorSimulacao(pasta_simulacao, largura)
    return EnviadorOutlook(cfg.get("conta_outlook", ""), bool(cfg.get("incluir_assinatura", True)),
                           largura)


def manter_pc_acordado(ligar: bool) -> None:
    """Evita que o Windows entre em suspensão durante o disparo (que dura horas)."""
    if sys.platform != "win32":
        return
    import ctypes
    es_continuous, es_system_required = 0x80000000, 0x00000001
    flags = es_continuous | (es_system_required if ligar else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)
