"""Informativo — sistema para gestão de informações capturadas em diversos
provedores (fontes).

Núcleo do sistema:

* :mod:`informativo.db` — camada fina sobre ``sqlite3``.
* :mod:`informativo.auth` — contas de usuário e autenticação (hash PBKDF2).
* :mod:`informativo.fontes` — cadastro das fontes de informação a buscar.
* :mod:`informativo.empresas` — cadastro de empresas (clientes) e seu nome de saída.
* :mod:`informativo.settings_repo` — configurações da aplicação (tema/cores).
* :mod:`informativo.themes` — paletas de tema (padrão azul, ao estilo QuitaCalc).
* :mod:`informativo.web` — interface web (Flask).
"""

__version__ = "0.1.0"
