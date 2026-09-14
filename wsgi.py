"""Ponto de entrada WSGI para servidores de produção (gunicorn, Render, etc.).

Expõe a variável ``app`` esperada por ``gunicorn wsgi:app``. A configuração
(DSN, chave de sessão, admin inicial) vem de variáveis de ambiente — ver
README, seção *Deploy no Render*.
"""

from informativoli.web import create_app

app = create_app()
