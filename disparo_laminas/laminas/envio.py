"""Envio dos e-mails: pelo Outlook, direto por SMTP ou em simulação.

- **Outlook** (COM/``pywin32``), como a macro fazia: sai pela conta padrão,
  por outra conta cadastrada no Outlook (ex.: a do subdomínio de prospecção)
  ou "enviar como" um endereço do subdomínio; fica nos Itens Enviados.
- **SMTP direto**: fala com o servidor de e-mail do subdomínio, sem Outlook.
- **Simulação**: grava cada e-mail como HTML para conferência.

A lâmina vai embutida no corpo (Content-ID), sem aparecer como anexo solto.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import smtplib
import ssl
import sys
import tempfile
import uuid
import webbrowser
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Optional

from . import segredo
from .config import descricao_remetente, dominio_do_email
from .mensagem import (Email, corpo_html, documento_html, inserir_no_inicio_do_body,
                       paragrafos_html)

_PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
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

    def __init__(self, conta: str = "", incluir_assinatura: bool = True, largura_max: int = 560,
                 enviar_como: str = "", responder_para: str = ""):
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
        self.enviar_como = enviar_como
        self.responder_para = responder_para

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
        if getattr(self, "enviar_como", ""):
            _etapa(f"definir o remetente De: ({self.enviar_como})",
                   setattr, mail, "SentOnBehalfOfName", self.enviar_como)
        if getattr(self, "responder_para", ""):
            for endereco in _enderecos(self.responder_para):
                _etapa(f"definir o Responder para ({endereco})", mail.ReplyRecipients.Add, endereco)

        src = None
        if email.imagem:
            anexo = self._anexar(mail, email.imagem, "a lâmina")
            cid = f"lamina-{uuid.uuid4().hex[:12]}"
            _etapa("embutir a lâmina no corpo",
                   lambda: anexo.PropertyAccessor.SetProperty(_PR_ATTACH_CONTENT_ID, cid))
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

    def enviar(self, email: Email) -> str:
        """Envia o e-mail. Devolve uma observação quando precisou de contorno.

        Em alguns Outlooks o ``Send`` direto (sem abrir a janela) é recusado
        com "Parâmetro incorreto"; nesse caso faz como a macro antiga: abre a
        janela do e-mail e envia em seguida.
        """
        mail = self._criar(email)
        try:
            mail.Send()
            return ""
        except Exception as exc:  # noqa: BLE001 - tenta como a macro
            erro_direto = descrever_erro(exc)
        try:
            mail.Display(False)
            mail.Send()
            return "Enviado abrindo a janela do e-mail (como a macro)"
        except Exception:  # noqa: BLE001 - último recurso: e-mail novo
            pass
        mail = self._criar(email)
        _etapa(f"abrir o e-mail (o Send direto falhou: {erro_direto})", mail.Display, False)
        _etapa(f"enviar (Send) — o Send direto também falhou: {erro_direto}", mail.Send)
        return "Enviado abrindo a janela do e-mail (2ª tentativa)"

    def exibir(self, email: Email) -> None:
        """Abre o e-mail pronto no Outlook, sem enviar (pré-visualização)."""
        mail = self._criar(email)
        _etapa("abrir a pré-visualização", mail.Display)


def _enderecos(texto: str) -> list[str]:
    return [x.strip() for x in (texto or "").replace(",", ";").split(";") if x.strip()]


class EnviadorSMTP:
    """Envia direto pelo servidor de e-mail (SMTP) do subdomínio de
    prospecção, sem passar pelo Outlook. Conecta a cada envio (com 3 minutos
    entre os e-mails, uma conexão aberta seria derrubada pelo servidor)."""

    def __init__(self, *, host: str, porta: int, seguranca: str, usuario: str, senha: str,
                 remetente_email: str, remetente_nome: str = "", responder_para: str = "",
                 assinatura: str = "", largura_max: int = 560, timeout: int = 60,
                 pasta_previa: Optional[Path] = None):
        faltando = [rotulo for valor, rotulo in ((host, "servidor"), (usuario, "usuário"),
                                                 (senha, "senha"), (remetente_email, "e-mail remetente"))
                    if not valor]
        if faltando:
            raise ErroEnvio("Envio SMTP sem " + ", ".join(faltando) + ". Complete em Configurações.")
        self.host, self.porta, self.seguranca = host.strip(), int(porta or 587), seguranca or "starttls"
        self.usuario, self.senha = usuario.strip(), senha
        self.remetente_email = remetente_email.strip()
        self.remetente_nome = remetente_nome.strip()
        self.responder_para = responder_para.strip()
        self.assinatura = assinatura or ""
        self.largura_max = largura_max
        self.timeout = timeout
        self.pasta_previa = Path(pasta_previa) if pasta_previa else Path(tempfile.gettempdir())

    def _conectar(self) -> smtplib.SMTP:
        contexto = ssl.create_default_context()
        if self.seguranca == "ssl":
            servidor = smtplib.SMTP_SSL(self.host, self.porta, timeout=self.timeout, context=contexto)
        else:
            servidor = smtplib.SMTP(self.host, self.porta, timeout=self.timeout)
            servidor.ehlo()
            if self.seguranca == "starttls":
                servidor.starttls(context=contexto)
                servidor.ehlo()
        try:
            servidor.login(self.usuario, self.senha)
        except Exception:
            servidor.close()
            raise
        return servidor

    def _executar(self, acao):
        try:
            servidor = self._conectar()
        except smtplib.SMTPAuthenticationError as exc:
            raise ErroEnvio(f"O servidor {self.host} recusou o usuário/senha do SMTP "
                            f"({exc.smtp_code}). Confira em Configurações; no Google/Microsoft "
                            "pode ser preciso uma senha de app.") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise ErroEnvio(f"Não foi possível conectar ao SMTP {self.host}:{self.porta} "
                            f"({self.seguranca}): {exc}") from exc
        try:
            return acao(servidor)
        except smtplib.SMTPRecipientsRefused as exc:
            recusados = ", ".join(exc.recipients)
            raise ErroEnvio(f"O servidor recusou o(s) destinatário(s): {recusados}") from exc
        except smtplib.SMTPSenderRefused as exc:
            raise ErroEnvio(f"O servidor recusou o remetente {self.remetente_email}: "
                            f"{exc.smtp_error!r}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise ErroEnvio(f"Falha no envio SMTP: {exc}") from exc
        finally:
            try:
                servidor.quit()
            except Exception:  # noqa: BLE001 - conexão já encerrada
                pass

    def montar(self, email: Email) -> EmailMessage:
        dominio = dominio_do_email(self.remetente_email) or None
        msg = EmailMessage()
        msg["From"] = formataddr((self.remetente_nome, self.remetente_email))
        msg["To"] = email.para
        if email.cc:
            msg["Cc"] = ", ".join(_enderecos(email.cc))
        if self.responder_para:
            msg["Reply-To"] = ", ".join(_enderecos(self.responder_para))
        msg["Subject"] = email.assunto
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=dominio)

        cid = make_msgid(domain=dominio) if email.imagem else None
        src = f"cid:{cid[1:-1]}" if cid else None
        html = documento_html(corpo_html(email, src, self.largura_max) + paragrafos_html(self.assinatura))
        texto = "\n\n".join(t.strip("\n") for t in (email.texto_inicio, email.texto_fim, self.assinatura)
                            if t and t.strip())
        msg.set_content(texto or " ")
        msg.add_alternative(html, subtype="html")
        if email.imagem:
            imagem = Path(email.imagem)
            if not imagem.is_file():
                raise ErroEnvio(f"Lâmina não encontrada: {imagem}")
            tipo, subtipo = (mimetypes.guess_type(imagem.name)[0] or "image/jpeg").split("/", 1)
            msg.get_payload()[1].add_related(imagem.read_bytes(), maintype=tipo, subtype=subtipo,
                                             cid=cid, filename=imagem.name, disposition="inline")
        for caminho in email.anexos:
            caminho = Path(caminho)
            if not caminho.is_file():
                raise ErroEnvio(f"Apresentação não encontrada: {caminho}")
            tipo, subtipo = (mimetypes.guess_type(caminho.name)[0]
                             or "application/octet-stream").split("/", 1)
            msg.add_attachment(caminho.read_bytes(), maintype=tipo, subtype=subtipo,
                               filename=caminho.name)
        return msg

    def enviar(self, email: Email) -> str:
        msg = self.montar(email)
        destinatarios = [email.para] + _enderecos(email.cc) + _enderecos(email.cco)
        self._executar(lambda s: s.send_message(msg, from_addr=self.remetente_email,
                                                to_addrs=destinatarios))
        return ""

    def exibir(self, email: Email) -> Path:
        """Gera o e-mail como arquivo .eml e abre (o Windows abre no Outlook)."""
        self.pasta_previa.mkdir(parents=True, exist_ok=True)
        destino = self.pasta_previa / f"previa_{datetime.now():%Y%m%d_%H%M%S}.eml"
        destino.write_bytes(bytes(self.montar(email)))
        if sys.platform == "win32":
            os.startfile(destino)  # noqa: S606 - abre no programa de e-mail padrão
        else:
            webbrowser.open(destino.resolve().as_uri())
        return destino

    def testar(self) -> str:
        self._executar(lambda s: s.noop())
        return f"Conexão e login OK em {self.host}:{self.porta} ({self.seguranca})."


class EnviadorSimulacao:
    """Não envia nada: grava cada e-mail como HTML na pasta ``simulacao``."""

    def __init__(self, pasta: Path, largura_max: int = 560, remetente: str = "",
                 responder_para: str = ""):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.largura_max = largura_max
        self.remetente = remetente
        self.responder_para = responder_para

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
            f"De: {self.remetente or '(padrão)'}<br>"
            f"Responder para: {self.responder_para or '(remetente)'}<br>"
            f"Para: {email.para}<br>CC: {email.cc}<br>CCO: {email.cco}<br>"
            f"Assunto: {email.assunto}<br>"
            f"Anexos: {', '.join(Path(a).name for a in email.anexos) or '(nenhum)'}</p><hr>"
        )
        destino.write_text(documento_html(cabecalho + corpo_html(email, src, self.largura_max)),
                           encoding="utf-8")
        return destino

    def enviar(self, email: Email) -> str:
        self._gravar(email)
        return ""

    def exibir(self, email: Email) -> None:
        webbrowser.open(Path(self._gravar(email)).resolve().as_uri())


def criar_enviador(cfg: dict, pasta_simulacao: Path):
    """Enviador conforme Configurações: simulação, SMTP ou Outlook."""
    largura = int(cfg.get("largura_imagem_px") or 560)
    modo = cfg.get("modo_envio", "outlook")
    remetente = (cfg.get("remetente_email") or "").strip()
    responder_para = (cfg.get("responder_para") or "").strip()
    if cfg.get("modo_simulacao"):
        return EnviadorSimulacao(pasta_simulacao, largura, remetente=descricao_remetente(cfg),
                                 responder_para=responder_para)
    if modo == "smtp":
        return EnviadorSMTP(
            host=cfg.get("smtp_host", ""), porta=int(cfg.get("smtp_porta") or 587),
            seguranca=cfg.get("smtp_seguranca", "starttls"), usuario=cfg.get("smtp_usuario", ""),
            senha=segredo.revelar(cfg.get("smtp_senha", "")), remetente_email=remetente,
            remetente_nome=cfg.get("remetente_nome", ""), responder_para=responder_para,
            assinatura=cfg.get("assinatura_smtp", ""), largura_max=largura,
            pasta_previa=Path(pasta_simulacao) / "previa")
    return EnviadorOutlook(
        remetente if modo == "outlook_conta" else "",
        bool(cfg.get("incluir_assinatura", True)), largura,
        enviar_como=remetente if modo == "outlook_enviar_como" else "",
        responder_para=responder_para)


def manter_pc_acordado(ligar: bool) -> None:
    """Evita que o Windows entre em suspensão durante o disparo (que dura horas)."""
    if sys.platform != "win32":
        return
    import ctypes
    es_continuous, es_system_required = 0x80000000, 0x00000001
    flags = es_continuous | (es_system_required if ligar else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)
