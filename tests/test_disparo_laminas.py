"""Testes do Disparo de Lâminas (núcleo, sem Outlook nem tela)."""

from __future__ import annotations

import queue
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "disparo_laminas"))

from laminas import config as cfgmod  # noqa: E402
from laminas.base import (DUPLICADO, INVALIDO, JA_ENVIADO, PENDENTE, Contato,  # noqa: E402
                          analisar, limpar_texto, registros)
from laminas.campanhas import (CAMPANHA_GERAL, lamina_do_envio, listar_campanhas,  # noqa: E402
                               listar_laminas)
from laminas.disparo import Disparo  # noqa: E402
from laminas.envio import EnviadorSimulacao  # noqa: E402
from laminas.historico import ENVIADO, ERRO, Historico  # noqa: E402
from laminas.mensagem import (corpo_html, dimensoes_imagem, inserir_no_inicio_do_body,  # noqa: E402
                              montar, preencher)

PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000320000002580806000000"
    "9a768270000000017352474200aece1ce90000000d49444154789c636000"
    "0000000200015e0f2d1d0000000049454e44ae426082"
)  # cabeçalho PNG 800x600


def _planilha(tmp_path, linhas, aba="A ENVIAR"):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = aba
    for linha in linhas:
        ws.append(linha)
    caminho = tmp_path / "base.xlsx"
    wb.save(caminho)
    return str(caminho)


@pytest.fixture()
def hist(tmp_path):
    return Historico(tmp_path / "h.db")


# -- base / duplicados ---------------------------------------------------------

def test_limpar_texto_remove_lixo_de_exportacao():
    assert limpar_texto("_x000D_\n\tBDO Brasil - BDO_x000D_\n") == "BDO Brasil - BDO"
    assert limpar_texto("\n            Dantas Distribuidora\n        ") == "Dantas Distribuidora"


def test_registros_reconhece_titulos_da_macro(tmp_path):
    caminho = _planilha(tmp_path, [
        ["Empresa", "Nome Completo", "E-mail", None],
        ["  Acme  ", "Ana Souza", " Ana@Acme.com.br ", "=VLOOKUP(...)"],
    ])
    regs = registros(caminho, "A ENVIAR")
    assert regs == [{"linha": 2, "empresa": "Acme", "nome": "Ana Souza",
                     "email": "Ana@Acme.com.br", "copia": "", "data": None, "status": ""}]


def test_colunas_em_qualquer_ordem_e_com_outros_titulos(tmp_path):
    caminho = _planilha(tmp_path, [
        ["Lista de prospecção - outubro"],  # linha de título acima do cabeçalho
        [],
        ["Cargo", "E-mail Principal", "Mensagem (parte de cima do e-mail)", "Razão Social", "Contato"],
        ["Diretora", "ana@acme.com", "texto", "Acme Ltda", "Ana Souza"],
    ])
    from laminas.base import ler_base
    regs, cab = ler_base(caminho, "A ENVIAR")
    assert (regs[0]["nome"], regs[0]["empresa"], regs[0]["email"]) == ("Ana Souza", "Acme Ltda", "ana@acme.com")
    assert cab.linha_titulo == 3
    assert cab.descricao("nome") == "E - Contato" and cab.descricao("email") == "B - E-mail Principal"


def test_primeiro_nome_mais_sobrenome_e_nome_da_empresa(tmp_path):
    caminho = _planilha(tmp_path, [
        ["Sobrenome", "Nome da Empresa", "Primeiro Nome", "Email"],
        ["Souza", "Acme", "Ana", "ana@acme.com"],
    ])
    reg = registros(caminho)[0]
    assert (reg["nome"], reg["empresa"]) == ("Ana Souza", "Acme")


def test_planilha_sem_titulos_e_escolha_manual_das_colunas(tmp_path):
    caminho = _planilha(tmp_path, [
        ["Acme", "Ana Souza", "ana@acme.com"],
        ["Beta", "Bia Lima", "bia@beta.com"],
    ])
    from laminas.base import ler_base
    regs, cab = ler_base(caminho)
    assert cab.linha_titulo == 0 and regs[0]["email"] == "ana@acme.com" and regs[0]["nome"] == ""
    regs, cab = ler_base(caminho, colunas={"empresa": 0, "nome": 1})
    assert len(regs) == 2 and (regs[1]["nome"], regs[1]["empresa"]) == ("Bia Lima", "Beta")


def test_titulos_genericos_nao_viram_contato(tmp_path):
    caminho = _planilha(tmp_path, [["Col1", "Col2", "Col3"], ["Gama", "Carla", "carla@gama.com"]])
    from laminas.base import ler_base
    regs, cab = ler_base(caminho, colunas={"empresa": 0, "nome": 1})
    assert cab.linha_titulo == 1 and cab.descricao("nome") == "B - Col2"
    assert [(r["linha"], r["nome"], r["empresa"]) for r in regs] == [(2, "Carla", "Gama")]


def test_registros_csv_com_ponto_e_virgula(tmp_path):
    caminho = tmp_path / "base.csv"
    caminho.write_text("Empresa;Nome;E-mail;Cópia\nAcme;Ana;ana@acme.com;S\n", encoding="utf-8")
    regs = registros(str(caminho))
    assert regs[0]["email"] == "ana@acme.com" and regs[0]["copia"] == "S"


def test_analisar_aponta_duplicados_ja_enviados_e_invalidos():
    regs = [
        {"linha": 2, "empresa": "A", "nome": "Ana", "email": "ana@a.com", "copia": "S"},
        {"linha": 3, "empresa": "A", "nome": "Ana 2", "email": "ANA@a.com ", "copia": ""},
        {"linha": 4, "empresa": "B", "nome": "Bia", "email": "bia@b.com", "copia": ""},
        {"linha": 5, "empresa": "C", "nome": "Caio", "email": "caio-sem-arroba", "copia": ""},
        {"linha": 6, "empresa": "", "nome": "Duda", "email": "duda@d.com", "copia": ""},
        {"linha": 7, "empresa": "A", "nome": "Ana 3", "email": "ana@a.com", "copia": ""},
    ]
    contatos, resumo = analisar(regs, {"bia@b.com": "2026-04-06 13:47:34"})
    sit = {c.linha: c.situacao for c in contatos}
    assert sit == {2: PENDENTE, 3: DUPLICADO, 4: JA_ENVIADO, 5: INVALIDO, 6: INVALIDO, 7: DUPLICADO}
    assert resumo.duplicados == {"ana@a.com": [2, 3, 7]}
    assert contatos[0].enviar and contatos[0].cc  # coluna Cópia = S já marca CC
    assert not contatos[2].enviar and "06/04/2026" in contatos[2].detalhe
    assert "empresa" in contatos[4].detalhe


# -- histórico -----------------------------------------------------------------

def test_historico_registra_conta_dia_e_dedup(hist):
    hist.registrar(email="Ana@A.com", nome="Ana", status=ENVIADO, data_hora="2026-10-27 09:00:00")
    hist.registrar(email="bia@b.com", status=ERRO, data_hora="2026-10-27 09:03:00")
    assert hist.enviados_no_dia(datetime(2026, 10, 27).date()) == 1
    assert hist.data_envio("ana@a.com") == "2026-10-27 09:00:00"
    assert hist.data_envio("bia@b.com") is None  # erro não conta como enviado
    assert set(hist.ja_enviados()) == {"ana@a.com"}


def test_historico_importa_relatorio_antigo_e_exporta(tmp_path, hist):
    caminho = _planilha(tmp_path, [
        ["Empresa", "Nome do Cliente", "E-mail Enviado", "Data", "Hora", "Status"],
        ["X", "Ana", "ana@a.com", datetime(2026, 4, 6), None, "Enviado"],
        ["X", "Bia", "bia@b.com", datetime(2026, 4, 6), None, "Erro"],
        ["X", "Ana", "ana@a.com", datetime(2026, 4, 7), None, "Enviado"],
    ], aba="RELATORIO")
    novos, ignorados = hist.importar(registros(caminho, "RELATORIO"), origem="teste")
    assert (novos, ignorados) == (1, 2)
    assert hist.data_envio("ana@a.com") == "2026-04-06 00:00:00"
    assert hist.enviados_no_dia(datetime(2026, 4, 6).date()) == 0  # importado não gasta limite

    destino = tmp_path / "enviados.xlsx"
    assert hist.exportar_xlsx(destino) == 1
    from openpyxl import load_workbook
    ws = load_workbook(destino)["ENVIADOS"]
    assert ws["D2"].value == "ana@a.com" and ws["I2"].value == "Importado"


# -- mensagem ------------------------------------------------------------------

def test_preencher_campos_novos_e_da_macro():
    c = Contato(linha=2, empresa="Acme", nome="Ana Souza", email="ana@acme.com")
    manha, tarde = datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 15)
    assert preencher("Olá {nome}, {saudacao}! ({empresa})", c, manha) == "Olá Ana Souza, bom dia! (Acme)"
    assert preencher("Olá <<Nome do Cliente>>, <diatarde>! {primeiro_nome}", c, tarde) == \
        "Olá Ana Souza, boa tarde! Ana"
    assert preencher("{desconhecido}", c, manha) == "{desconhecido}"


def test_montar_so_poe_cc_nos_marcados(tmp_path):
    msg = cfgmod.mensagem_da_campanha(cfgmod.DEFAULTS, "corporativo")
    com = Contato(2, "Acme", "Ana", "ana@acme.com", cc=True)
    sem = Contato(3, "Acme", "Bia", "bia@acme.com", cc=False)
    assert montar(com, msg, imagem=None, cc="ricardo@x.com").cc == "ricardo@x.com"
    assert montar(sem, msg, imagem=None, cc="ricardo@x.com").cc == ""
    assert montar(com, msg, imagem=None).assunto.startswith("CONFIRMANDO REUNIÃO com Ana da Acme")


def test_corpo_html_limita_largura_e_assinatura(tmp_path):
    img = tmp_path / "l.png"
    img.write_bytes(PNG_1x1)
    assert dimensoes_imagem(img) == (800, 600)
    c = Contato(2, "Acme", "Ana <b>", "ana@acme.com")
    email = montar(c, {"assunto": "x", "texto_inicio": "Olá {nome}\nlinha 2", "texto_fim": "Tchau"},
                   imagem=img)
    html = corpo_html(email, "cid:abc", 560)
    assert 'width="560" height="420"' in html and "Ana &lt;b&gt;" in html and "<br>" in html
    assinado = inserir_no_inicio_do_body('<html><body lang=PT-BR><p>Assinatura</p></body></html>', "<p>Oi</p>")
    assert assinado.index("Oi") < assinado.index("Assinatura")


# -- campanhas -------------------------------------------------------------------

def test_campanhas_e_rodizio_de_laminas(tmp_path):
    (tmp_path / "CORPORATIVO").mkdir()
    (tmp_path / "EVENTOS").mkdir()
    (tmp_path / "VAZIA").mkdir()
    for nome in ("a.jpeg", "b.png"):
        (tmp_path / "CORPORATIVO" / nome).write_bytes(PNG_1x1)
    (tmp_path / "EVENTOS" / "e.jpg").write_bytes(PNG_1x1)
    (tmp_path / "solta.png").write_bytes(PNG_1x1)
    assert listar_campanhas(str(tmp_path)) == ["CORPORATIVO", "EVENTOS", CAMPANHA_GERAL]
    laminas = listar_laminas(str(tmp_path), "CORPORATIVO")
    assert {p.name for p in laminas} == {"a.jpeg", "b.png"}
    assert [lamina_do_envio(laminas, i, True) for i in range(3)] == [laminas[0], laminas[1], laminas[0]]
    assert lamina_do_envio(laminas, 5, False) == laminas[0]
    assert listar_campanhas(str(tmp_path / "nao-existe")) == []


def test_config_mensagem_por_campanha(tmp_path):
    caminho = tmp_path / "config.json"
    cfg = cfgmod.carregar(caminho)
    cfg["mensagens"]["EVENTOS"] = {"assunto": "Eventos", "texto_inicio": "", "texto_fim": ""}
    cfg["limite_diario"] = 50
    cfgmod.salvar(cfg, caminho)
    lido = cfgmod.carregar(caminho)
    assert lido["limite_diario"] == 50 and lido["intervalo_minutos"] == 3.0
    assert cfgmod.mensagem_da_campanha(lido, "EVENTOS")["assunto"] == "Eventos"
    assert cfgmod.mensagem_da_campanha(lido, "CORPORATIVO")["assunto"].startswith("CONFIRMANDO")


# -- disparo ---------------------------------------------------------------------

class _Relogio:
    """Relógio falso: ``espera`` avança o tempo sem dormir."""

    def __init__(self):
        self.t = 0.0
        self.esperas: list[float] = []

    def __call__(self):
        return self.t


class _Enviador:
    def __init__(self, falhar=()):
        self.enviados = []
        self.falhar = set(falhar)

    def enviar(self, email):
        if email.para in self.falhar:
            raise RuntimeError("caixa cheia")
        self.enviados.append(email)


def _disparo(contatos, hist, enviador, relogio, **kw):
    eventos = queue.Queue()
    params = dict(historico=hist, criar_enviador=lambda: enviador,
                  mensagem={"assunto": "Oi {nome}", "texto_inicio": "", "texto_fim": ""},
                  campanha="CORPORATIVO", laminas=[Path("a.png"), Path("b.png")],
                  alternar_laminas=True, email_copia="ricardo@x.com", copia_oculta="",
                  limite_diario=80, intervalo_seg=180, eventos=eventos,
                  agora=lambda: datetime(2026, 10, 27, 10, 0), relogio=relogio)
    params.update(kw)
    d = Disparo(contatos, **params)

    def esperar(segundos):  # substitui o Event.wait real
        relogio.esperas.append(segundos)
        relogio.t += segundos
        return False
    d._parar.wait = esperar
    return d, eventos


def _eventos(fila):
    saida = []
    while not fila.empty():
        saida.append(fila.get())
    return saida


def test_disparo_intervalo_cc_rodizio_e_registro(hist):
    contatos = [Contato(i, "Acme", f"N{i}", f"n{i}@acme.com", enviar=True, cc=(i < 2))
                for i in range(4)]
    relogio = _Relogio()
    enviador = _Enviador()
    d, fila = _disparo(contatos, hist, enviador, relogio)
    d.run()
    assert [e.para for e in enviador.enviados] == [c.email for c in contatos]
    assert [e.cc for e in enviador.enviados] == ["ricardo@x.com", "ricardo@x.com", "", ""]
    assert [e.imagem.name for e in enviador.enviados] == ["a.png", "b.png", "a.png", "b.png"]
    assert relogio.esperas == [180, 180, 180]  # 1º sai na hora, depois 3 min entre cada
    assert hist.enviados_no_dia(datetime(2026, 10, 27).date()) == 4
    tipo, dados = _eventos(fila)[-1]
    assert tipo == "fim" and dados["enviados"] == 4


def test_disparo_respeita_limite_diario_contando_envios_anteriores(hist):
    # O histórico grava a hora real do envio, então o "dia" do teste é hoje.
    hoje = datetime.now().strftime("%Y-%m-%d")
    for i in range(78):
        hist.registrar(email=f"antes{i}@x.com", status=ENVIADO, data_hora=f"{hoje} 00:00:{i % 60:02d}")
    contatos = [Contato(i, "Acme", f"N{i}", f"n{i}@acme.com", enviar=True) for i in range(5)]
    enviador = _Enviador()
    d, fila = _disparo(contatos, hist, enviador, _Relogio(), agora=datetime.now)
    d.run()
    assert len(enviador.enviados) == 2
    tipo, dados = _eventos(fila)[-1]
    assert "Limite diário de 80" in dados["motivo"]


def test_disparo_pula_ja_enviado_salvo_reenvio_autorizado_e_registra_erro(hist):
    hist.registrar(email="velho@x.com", status=ENVIADO, data_hora="2026-01-01 10:00:00")
    hist.registrar(email="forca@x.com", status=ENVIADO, data_hora="2026-01-01 10:00:00")
    contatos = [
        Contato(2, "A", "Velho", "velho@x.com", enviar=True),
        Contato(3, "A", "Força", "forca@x.com", enviar=True, forcar=True),
        Contato(4, "A", "Falha", "falha@x.com", enviar=True),
    ]
    enviador = _Enviador(falhar={"falha@x.com"})
    d, fila = _disparo(contatos, hist, enviador, _Relogio())
    d.run()
    assert [e.para for e in enviador.enviados] == ["forca@x.com"]
    tipos = [t for t, _ in _eventos(fila)]
    assert "pulado" in tipos and "erro" in tipos
    erros = [r for r in hist.listar() if r["status"] == ERRO]
    assert erros[0]["email"] == "falha@x.com" and erros[0]["erro"] == "caixa cheia"


def test_disparo_parar_interrompe_na_espera(hist):
    contatos = [Contato(i, "A", f"N{i}", f"n{i}@a.com", enviar=True) for i in range(3)]
    enviador = _Enviador()
    d, fila = _disparo(contatos, hist, enviador, _Relogio())
    d._parar.wait = lambda s: True  # usuário clicou em Parar durante a espera
    d.run()
    assert len(enviador.enviados) == 1
    assert "interrompido" in _eventos(fila)[-1][1]["motivo"]


def test_enviador_simulacao_gera_html(tmp_path):
    img = tmp_path / "l.png"
    img.write_bytes(PNG_1x1)
    c = Contato(2, "Acme", "Ana", "ana@acme.com", cc=True)
    email = montar(c, {"assunto": "Oi", "texto_inicio": "Olá", "texto_fim": "Até"}, imagem=img, cc="r@x.com")
    EnviadorSimulacao(tmp_path / "sim").enviar(email)
    arquivos = list((tmp_path / "sim").glob("*.html"))
    assert len(arquivos) == 1
    conteudo = arquivos[0].read_text(encoding="utf-8")
    assert "CC: r@x.com" in conteudo and 'src="l.png"' in conteudo
