"""Envio pelo Outlook instalado no PC (ou simulação em arquivos HTML).

O Outlook é controlado via COM (``pywin32``), como a macro fazia: o e-mail
sai pela conta do Outlook e fica nos Itens Enviados. A lâmina vai embutida no
corpo (anexo com Content-ID), sem aparecer como anexo solto.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from .mensagem import Email, corpo_html, documento_html, inserir_no_inicio_do_body

_PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
_PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
_DISPID_SEND_USING_ACCOUNT = 64209


# Códigos de erro COM mais comuns, com uma explicação em português.
_DICAS_COM = {
    0x80070057: "o Outlook recusou um dos dados (parâmetro incorreto)",
    0x80004005: "falha genérica do Outlook",
    0x8004010F: "conta ou perfil do Outlook não encontrado",
    0x80040109: "o item já foi enviado ou excluído",
    0x80070005: "acesso negado (o Outlook bloqueou a automação ou o arquivo)",
    0x800CCC0F: "a conexão com o servidor foi interrompida",
}


class ErroEnvio(Exception):
    pass


def descrever_erro(exc: BaseException) -> str:
    """Texto legível para erros COM (``pywintypes.com_error``) e outros."""
    if isinstance(exc, ErroEnvio):
        return str(exc)
    args = getattr(exc, "args", ())
    if len(args) >= 2 and isinstance(args[0], int):
        codigo = args[0] & 0xFFFFFFFF
        detalhe = str(args[1] or "")
        info = args[2] if len(args) > 2 else None
        if info and len(info) > 2 and info[2]:  # descrição dada pelo próprio Outlook
            detalhe = str(info[2])
            if len(info) > 5 and isinstance(info[5], int) and info[5]:
                codigo = info[5] & 0xFFFFFFFF
        dica = _DICAS_COM.get(codigo)
        return f"{detalhe.strip()} [0x{codigo:08X}]" + (f" — {dica}" if dica else "")
    return str(exc) or exc.__class__.__name__


def _etapa(descricao: str, funcao, *args):
    """Executa uma etapa do Outlook; se falhar, diz qual etapa foi."""
    try:
        return funcao(*args)
    except ErroEnvio:
        raise
    except Exception as exc:  # noqa: BLE001 - erro COM traduzido
        raise ErroEnvio(f"Falha ao {descricao}: {descrever_erro(exc)}") from exc


def copia_local(caminho: Path) -> Path:
    """Cópia do arquivo numa pasta temporária local. Contorna arquivos do
    OneDrive que estão só na nuvem e caminhos que o Outlook não aceita."""
    destino_dir = Path(tempfile.gettempdir()) / "disparo_laminas"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / caminho.name
    origem = caminho.stat()
    if not destino.exists() or destino.stat().st_size != origem.st_size \
            or destino.stat().st_mtime < origem.st_mtime:
        shutil.copy2(caminho, destino)
    return destino


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

    def _novo_item(self):
        """Cria o e-mail; com conta definida, faz ele sair por essa conta."""
        if self.conta is None:
            return _etapa("criar o e-mail no Outlook", self.app.CreateItem, 0)
        mail = _etapa("criar o e-mail no Outlook", self.app.CreateItem, 0)
        try:
            mail.SendUsingAccount = self.conta
            return mail
        except Exception:  # noqa: BLE001 - tenta os contornos abaixo
            pass
        try:  # contorno conhecido do pywin32 para SendUsingAccount
            mail._oleobj_.Invoke(_DISPID_SEND_USING_ACCOUNT, 0, 8, 0, self.conta)
            return mail
        except Exception:  # noqa: BLE001
            pass
        # Último recurso: cria o e-mail nos Rascunhos da própria conta.
        rascunhos = _etapa(f"usar a conta '{self.conta.SmtpAddress}' do Outlook",
                           lambda: self.conta.DeliveryStore.GetDefaultFolder(16))
        return _etapa(f"usar a conta '{self.conta.SmtpAddress}' do Outlook", rascunhos.Items.Add, 0)

    def _anexar(self, mail, caminho: Path, descricao: str):
        """Anexa o arquivo; se o Outlook recusar o caminho original (OneDrive,
        caracteres especiais...), tenta de novo com uma cópia local."""
        caminho = Path(caminho)
        if not caminho.is_file():
            raise ErroEnvio(f"{descricao.capitalize()} não encontrada: {caminho}")
        try:
            return mail.Attachments.Add(os.path.abspath(caminho))
        except Exception:  # noqa: BLE001 - tenta com a cópia local
            pass
        local = _etapa(f"copiar {descricao} ({caminho.name}) para uma pasta local", copia_local, caminho)
        return _etapa(f"anexar {descricao} ({caminho.name})", mail.Attachments.Add, str(local))

    def _criar(self, email: Email):
        mail = self._novo_item()
        _etapa(f"preencher o destinatário ({email.para})", setattr, mail, "To", email.para)
        if email.cc:
            _etapa(f"preencher a cópia CC ({email.cc})", setattr, mail, "CC", email.cc)
        if email.cco:
            _etapa(f"preencher a cópia oculta ({email.cco})", setattr, mail, "BCC", email.cco)
        _etapa("preencher o assunto", setattr, mail, "Subject", email.assunto)

        src = None
        if email.imagem:
            anexo = self._anexar(mail, email.imagem, "a lâmina")
            cid = f"lamina-{uuid.uuid4().hex[:12]}"
            _etapa("embutir a lâmina no corpo",
                   lambda: anexo.PropertyAccessor.SetProperty(_PR_ATTACH_CONTENT_ID, cid))
            try:
                anexo.PropertyAccessor.SetProperty(_PR_ATTACHMENT_HIDDEN, True)
            except Exception:  # noqa: BLE001 - só estético
                pass
            src = f"cid:{cid}"

        for caminho in email.anexos:
            self._anexar(mail, caminho, "a apresentação")

        fragmento = corpo_html(email, src, self.largura_max)
        if self.incluir_assinatura:
            base = _etapa("carregar a assinatura do Outlook", lambda: (mail.GetInspector, mail.HTMLBody)[1])
            html = inserir_no_inicio_do_body(base or "", fragmento)
        else:
            html = documento_html(fragmento)
        _etapa("montar o corpo do e-mail", setattr, mail, "HTMLBody", html)
        return mail

    def enviar(self, email: Email) -> None:
        mail = self._criar(email)
        _etapa("enviar (Send)", mail.Send)

    def exibir(self, email: Email) -> None:
        """Abre o e-mail pronto no Outlook, sem enviar (pré-visualização)."""
        mail = self._criar(email)
        _etapa("abrir a pré-visualização", mail.Display)


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
