"""InformaTivoli — sistema para gestão de informações capturadas em diversos
provedores (fontes).

Núcleo do sistema:

* :mod:`informativoli.db` — camada fina sobre ``sqlite3``.
* :mod:`informativoli.auth` — contas de usuário e autenticação (hash PBKDF2).
* :mod:`informativoli.fontes` — cadastro das fontes de informação a buscar.
* :mod:`informativoli.settings_repo` — configurações da aplicação (tema/cores).
* :mod:`informativoli.themes` — paletas de tema (padrão azul, ao estilo QuitaCalc).
* :mod:`informativoli.web` — interface web (Flask).
"""

__version__ = "0.1.0"
