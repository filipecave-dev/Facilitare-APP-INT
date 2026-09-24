"""Testes do cliente Omniroute e do repositório de captações."""

from __future__ import annotations

import io
import json

import pytest

from informativo.db import Database, init_db
from informativo.fontes import FonteRepository
from informativo.omniroute import (
    CaptacaoRepository,
    OmnirouteClient,
    OmnirouteError,
    prompt_parafrase,
    prompt_para_fonte,
)


@pytest.fixture()
def db(tmp_path):
    with Database(f"sqlite:///{tmp_path}/o.db") as conexao:
        init_db(conexao)
        yield conexao


def test_endpoint_openai_compat():
    assert OmnirouteClient("http://x:20128").  _endpoint() == "http://x:20128/v1/chat/completions"
    assert OmnirouteClient("http://x/v1")._endpoint() == "http://x/v1/chat/completions"
    assert (
        OmnirouteClient("http://x/v1/chat/completions")._endpoint()
        == "http://x/v1/chat/completions"
    )
    # barra final é normalizada
    assert OmnirouteClient("http://x:20128/")._endpoint() == "http://x:20128/v1/chat/completions"


def test_configurado():
    assert OmnirouteClient("http://x", modelo="m").configurado()
    assert not OmnirouteClient("", modelo="m").configurado()
    assert not OmnirouteClient("http://x", modelo="").configurado()


def test_chat_parseia_resposta(monkeypatch):
    payload = {"choices": [{"message": {"content": "  Olá  "}}]}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        # confere que o corpo tem o modelo e as mensagens
        corpo = json.loads(req.data.decode())
        assert corpo["model"] == "meu-modelo"
        assert corpo["messages"][-1]["role"] == "user"
        return _Resp(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cli = OmnirouteClient("http://x", api_key="k", modelo="meu-modelo")
    assert cli.chat("oi") == "Olá"


def test_chat_sem_config_levanta():
    with pytest.raises(OmnirouteError):
        OmnirouteClient("", modelo="m").chat("oi")
    with pytest.raises(OmnirouteError):
        OmnirouteClient("http://x", modelo="").chat("oi")


def test_prompt_para_fonte_usa_dados(db):
    repo = FonteRepository(db)
    f = repo.criar("Reuters", "reuters.com", categoria="Geral", regiao="Internacional")
    system, prompt = prompt_para_fonte(f)
    assert "analista" in system.lower()
    assert "Reuters" in prompt and "Internacional" in prompt


def test_captacao_repository(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    assert cap.count() == 0
    cap.registrar(f, "resumo de teste")
    assert cap.count() == 1
    recentes = cap.listar_recentes()
    assert recentes[0]["fonte_nome"] == "Reuters"
    assert recentes[0]["conteudo"] == "resumo de teste"


def test_reclassificar_e_parafrasear(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    cap.registrar(f, "resumo original")
    cid = cap.listar_recentes()[0]["id"]
    # reclassificar em uma frente (mesmo após aprovado)
    cap.definir_status(cid, "aprovada")
    cap.definir_frente(cid, "Alerta")
    assert cap.get(cid)["frente"] == "Alerta"
    with pytest.raises(ValueError):
        cap.definir_frente(cid, "Inexistente")
    # limpar frente com vazio
    cap.definir_frente(cid, "")
    assert cap.get(cid)["frente"] is None
    # guardar paráfrase
    cap.definir_parafrase(cid, "texto reescrito")
    assert cap.get(cid)["parafrase"] == "texto reescrito"


def test_limpar_captacoes_por_status(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    cap.registrar(f, "a")
    cap.registrar(f, "b")
    ids = [c["id"] for c in cap.listar_recentes()]
    cap.definir_status(ids[0], "aprovada")
    # limpa só as pendentes
    assert cap.limpar(status="pendente") == 1
    assert cap.count() == 1
    # limpa tudo
    assert cap.limpar() == 1
    assert cap.count() == 0


def test_prioridade_ordena_desastre_e_aviacao():
    from informativo.priorizacao import prioridade_da_noticia

    desastre = prioridade_da_noticia("Enchente e deslizamento no litoral", "Brasil")
    greve_aero = prioridade_da_noticia("Greve de controladores fecha aeroporto de Guarulhos", "Brasil")
    viagem = prioridade_da_noticia("Nova rota de ônibus de turismo", "Brasil")
    neutra = prioridade_da_noticia("Balanço trimestral de uma empresa de software", "Brasil")
    assert desastre > viagem > neutra
    assert greve_aero > viagem
    # Brasil dá bônus sobre o mesmo fato fora do país.
    assert prioridade_da_noticia("aeroporto fechado", "Brasil") > \
        prioridade_da_noticia("aeroporto fechado", "Internacional")


def test_dedup_captacao_nao_repete(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    texto = "Greve de pilotos afeta voos no aeroporto de Congonhas nesta semana."
    id1 = cap.registrar(f, texto)
    assert id1 is not None
    # mesmo conteúdo: ignorado (retorna None)
    assert cap.registrar(f, texto) is None
    # quase igual: também ignorado por similaridade
    quase = "Greve de pilotos afeta os voos no aeroporto de Congonhas nesta semana toda."
    assert cap.registrar(f, quase) is None
    # conteúdo diferente entra normalmente
    assert cap.registrar(f, "Feira de tecnologia acontece em Recife com novidades.") is not None
    assert cap.count() == 2


def test_captacao_ordena_por_prioridade(db):
    repo_f = FonteRepository(db)
    f = repo_f.criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    cap.registrar(f, "Relatório sobre mercado de cafés especiais.")  # baixa
    cap.registrar(f, "Terremoto e tsunami atingem região costeira.", empresa_id=None)  # alta
    recentes = cap.listar_recentes()
    assert "Terremoto" in recentes[0]["conteudo"]  # prioridade alta primeiro


def test_atribuir_empresa_captacao(db):
    from informativo.empresas import EmpresaRepository

    er = EmpresaRepository(db)
    tivo = er.criar("Tivolitur", nome_solucao="Tivolitur")
    outra = er.criar("Outra", nome_solucao="Outra")
    f = FonteRepository(db).criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    a = cap.registrar(f, "Notícia um sobre aviação em SP.")
    b = cap.registrar(f, "Notícia dois totalmente diferente aqui.")
    # por item
    cap.definir_empresa(a, tivo.id)
    assert cap.get(a)["empresa_id"] == tivo.id
    # em massa: só as sem empresa vão para Tivolitur (a já tem)
    n = cap.atribuir_empresa_em_massa(tivo.id)
    assert n == 1  # apenas 'b'
    assert cap.get(b)["empresa_id"] == tivo.id
    # incluir as que já têm empresa: reatribui tudo para 'outra'
    n2 = cap.atribuir_empresa_em_massa(outra.id, apenas_sem_empresa=False)
    assert n2 == 2
    assert cap.get(a)["empresa_id"] == outra.id and cap.get(b)["empresa_id"] == outra.id


def test_normalizar_modelo_gemini(db):
    from informativo.provedores import ProvedorRepository

    repo = ProvedorRepository(db)
    p = repo.criar(
        "Gemini", "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-flash-lite-latest",
    )
    outro = repo.criar("DeepSeek", "openai", "https://api.deepseek.com", "deepseek-chat")
    n = repo.normalizar_modelo_gemini()
    assert n == 1
    assert repo.get(p.id).modelo == "gemini-2.5-flash-lite"
    assert repo.get(outro.id).modelo == "deepseek-chat"  # inalterado
    # idempotente
    assert repo.normalizar_modelo_gemini() == 0


def test_metricas_do_painel(db):
    repo_f = FonteRepository(db)
    fa = repo_f.criar("Reuters", "reuters.com")
    fb = repo_f.criar("G1", "g1.com")
    cap = CaptacaoRepository(db)
    # Reuters: 2 captações, 1 aprovada (com paráfrase e disparo) e 1 descartada
    a1 = cap.registrar(fa, "Alpha greve aeroporto Guarulhos hoje.")
    a2 = cap.registrar(fa, "Beta enchente litoral norte agora.")
    cap.definir_status(a1, "aprovada"); cap.definir_parafrase(a1, "reescrito")
    cap.definir_frente(a1, "Alerta"); cap.definir_disparado(a1)
    cap.definir_status(a2, "descartada")
    # G1: 1 captação sem aprovação (fonte sem relevância)
    b1 = cap.registrar(fb, "Gama feira gastronomia centro cidade.")
    cap.definir_status(b1, "descartada")

    m = cap.metricas()
    assert m["captadas"] == 3
    assert m["aprovadas"] == 1 and m["descartadas"] == 2
    assert m["parafraseadas"] == 1 and m["disparadas"] == 1
    assert m["fontes_consultadas"] == 2
    assert m["ultima_captacao"] and m["ultimo_disparo"]

    top = cap.top_fontes(5)
    assert top[0]["fonte_nome"] == "Reuters" and top[0]["total"] == 2
    assert top[0]["aprovadas"] == 1

    fracas = {f["fonte_nome"] for f in cap.fontes_sem_relevancia(5)}
    assert "G1" in fracas and "Reuters" not in fracas  # Reuters teve 1 aprovada

    frentes = cap.por_frente()
    assert frentes["Alerta"] == 1

    serie = cap.serie_diaria(14)
    assert sum(d["n"] for d in serie) == 3


def test_definir_disparado_toggle(db):
    f = FonteRepository(db).criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    cid = cap.registrar(f, "Notícia para disparo.")
    assert cap.get(cid)["disparado_em"] is None
    cap.definir_disparado(cid, True)
    assert cap.get(cid)["disparado_em"] is not None
    cap.definir_disparado(cid, False)
    assert cap.get(cid)["disparado_em"] is None


def test_retencao_expurga_antigas(db):
    from datetime import datetime, timedelta, timezone

    from informativo.empresas import EmpresaRepository

    e = EmpresaRepository(db).criar("ACME", nome_solucao="ACME")
    f = FonteRepository(db).criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    a = cap.registrar(f, "Notícia recente distinta aeroporto.", empresa_id=e.id)
    b = cap.registrar(f, "Notícia antiga totalmente diferente enchente.", empresa_id=e.id)
    # envelhece a 'b' para 40 dias atrás
    velho = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db.execute("UPDATE captacoes SET criado_em = ? WHERE id = ?", (velho, b))
    db.commit()
    # retenção de 30 dias remove só a antiga
    n = cap.expurgar_antigas(30, empresa_id=e.id, somente_empresa=True)
    assert n == 1
    assert cap.get(a) is not None and cap.get(b) is None
    # dias<=0 não remove nada
    assert cap.expurgar_antigas(0, empresa_id=e.id, somente_empresa=True) == 0


def test_expurgar_por_retencao_por_empresa(db):
    from datetime import datetime, timedelta, timezone

    from informativo.empresas import EmpresaRepository
    from informativo.omniroute import expurgar_por_retencao

    er = EmpresaRepository(db)
    a = er.criar("A", nome_solucao="A")
    b = er.criar("B", nome_solucao="B")
    er.atualizar(a.id, dias_retencao=15)   # A expurga com 15 dias
    er.atualizar(b.id, dias_retencao=0)    # B mantém tudo
    f = FonteRepository(db).criar("Reuters", "reuters.com")
    cap = CaptacaoRepository(db)
    ca = cap.registrar(f, "Alpha antiga empresa A greve.", empresa_id=a.id)
    cb = cap.registrar(f, "Bravo antiga empresa B enchente.", empresa_id=b.id)
    velho = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    db.execute("UPDATE captacoes SET criado_em = ?", (velho,))
    db.commit()
    total = expurgar_por_retencao(db)
    assert total == 1  # só a da empresa A
    assert cap.get(ca) is None and cap.get(cb) is not None


def test_prompt_parafrase_tem_frente_e_conteudo(db):
    cap = {
        "fonte_nome": "Reuters", "regiao": "Brasil",
        "frente": "Notícias de Mercado", "conteudo": "texto base",
    }
    system, prompt = prompt_parafrase(cap, nome_solucao="Boletim ACME")
    assert "paráfrase" in system.lower() or "reescreva" in system.lower()
    assert "Notícias de Mercado" in system
    assert "texto base" in prompt and "Boletim ACME" in prompt
