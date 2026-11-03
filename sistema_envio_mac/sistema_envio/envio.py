"""Envio dos e-mails: direto por SMTP (servidor do subdomínio) ou simulação.

- **SMTP direto**: fala com o servidor de e-mail do subdomínio de
  prospecção; não depende de Outlook nem do app Mail.
- **Simulação**: grava cada e-mail como HTML para conferência.

A lâmina vai embutida no corpo (Content-ID), sem aparecer como anexo solto.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import smtplib
import ssl
import subprocess
import sys
import tempfile
import webbrowser
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Optional

from . import segredo
from .config import descricao_remetente, dominio_do_email
from .mensagem import Email, corpo_html, documento_html, paragrafos_html


class ErroEnvio(Exception):
    pass


def descrever_erro(exc: BaseException) -> str:
    """Texto legível para o erro (mostrado na tela e gravado no histórico)."""
    return str(exc) or exc.__class__.__name__


def contexto_ssl() -> ssl.SSLContext:
    """Contexto TLS com os certificados do pacote ``certifi``. O Python do
    python.org no Mac não usa os certificados do sistema e, sem isso, toda
    conexão segura falha com CERTIFICATE_VERIFY_FAILED."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def abrir(caminho: Path) -> None:
    """Abre arquivo ou pasta no app padrão (Finder, Mail, navegador...)."""
    caminho = Path(caminho)
    if sys.platform == "darwin":
        subprocess.run(["open", str(caminho)], check=False)
    else:
        webbrowser.open(caminho.resolve().as_uri())


def _enderecos(texto: str) -> list[str]:
    return [x.strip() for x in (texto or "").replace(",", ";").split(";") if x.strip()]


class EnviadorSMTP:
    """Envia direto pelo servidor de e-mail (SMTP) do subdomínio de
    prospecção, sem depender de app de e-mail. Conecta a cada envio (com 3 minutos
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
        contexto = contexto_ssl()
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
        """Gera o e-mail como arquivo .eml e abre (no Mac, no app Mail)."""
        self.pasta_previa.mkdir(parents=True, exist_ok=True)
        destino = self.pasta_previa / f"previa_{datetime.now():%Y%m%d_%H%M%S}.eml"
        destino.write_bytes(bytes(self.montar(email)))
        abrir(destino)  # no Mac abre no app Mail, já formatado
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
        abrir(self._gravar(email))


def criar_enviador(cfg: dict, pasta_simulacao: Path):
    """Enviador conforme Configurações: simulação ou SMTP."""
    largura = int(cfg.get("largura_imagem_px") or 560)
    responder_para = (cfg.get("responder_para") or "").strip()
    if cfg.get("modo_simulacao"):
        return EnviadorSimulacao(pasta_simulacao, largura, remetente=descricao_remetente(cfg),
                                 responder_para=responder_para)
    return EnviadorSMTP(
        host=cfg.get("smtp_host", ""), porta=int(cfg.get("smtp_porta") or 587),
        seguranca=cfg.get("smtp_seguranca", "starttls"), usuario=cfg.get("smtp_usuario", ""),
        senha=segredo.revelar(cfg.get("smtp_senha", "")),
        remetente_email=(cfg.get("remetente_email") or "").strip(),
        remetente_nome=cfg.get("remetente_nome", ""), responder_para=responder_para,
        assinatura=cfg.get("assinatura_smtp", ""), largura_max=largura,
        pasta_previa=Path(pasta_simulacao) / "previa")


_cafeina: Optional[subprocess.Popen] = None


def manter_mac_acordado(ligar: bool) -> None:
    """Impede o Mac de dormir durante o disparo (que dura horas) com o
    ``caffeinate`` do macOS. Fechar a tampa ainda põe o Mac para dormir,
    a não ser que ele esteja na tomada com monitor externo."""
    global _cafeina
    if sys.platform != "darwin":
        return
    if ligar and _cafeina is None:
        try:
            _cafeina = subprocess.Popen(["caffeinate", "-ims", "-w", str(os.getpid())])
        except OSError:
            _cafeina = None
    elif not ligar and _cafeina is not None:
        _cafeina.terminate()
        _cafeina = None
