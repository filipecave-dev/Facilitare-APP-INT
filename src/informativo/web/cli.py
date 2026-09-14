"""CLI da aplicação web do Informativo.

Subcomandos:

* ``create-admin`` — cria (ou atualiza) o usuário administrador.
* ``create-user``  — cria um usuário com perfil arbitrário.
* ``run``          — sobe o servidor de desenvolvimento.

A senha **nunca** é lida de um valor fixo no código: use ``--password`` na sua
máquina ou a variável de ambiente ``INFORMATIVO_ADMIN_PASSWORD`` /
``INFORMATIVO_USER_PASSWORD``. Ela é gravada apenas como hash PBKDF2.

Exemplos::

    export INFORMATIVO_ADMIN_PASSWORD='sua-senha-forte'
    informativo-web create-admin --dsn sqlite:///output/informativo.db
    informativo-web run --port 8000
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Optional

from ..auth import UsuarioRepository
from ..db import Database, init_db
from ..fontes import FonteRepository
from . import DSN_PADRAO


def _resolver_senha(cli_valor: Optional[str], env_var: str) -> str:
    senha = cli_valor or os.environ.get(env_var)
    if not senha:
        senha = getpass.getpass("Senha: ")
    if not senha or len(senha) < 8:
        raise SystemExit("Senha inválida (mínimo 8 caracteres).")
    return senha


def _cmd_create_admin(args) -> int:
    senha = _resolver_senha(args.password, "INFORMATIVO_ADMIN_PASSWORD")
    with Database(args.dsn) as db:
        init_db(db)
        conta = UsuarioRepository(db).criar(
            args.username,
            senha,
            "Administrador",
            nome=args.nome or "Administrador",
            atualizar_se_existir=True,
        )
    print(f"Admin pronto: {conta.username!r} (perfil {conta.perfil}).")
    return 0


def _cmd_create_user(args) -> int:
    senha = _resolver_senha(args.password, "INFORMATIVO_USER_PASSWORD")
    with Database(args.dsn) as db:
        init_db(db)
        try:
            conta = UsuarioRepository(db).criar(
                args.username,
                senha,
                args.perfil,
                nome=args.nome,
                atualizar_se_existir=args.atualizar,
            )
        except ValueError as exc:
            raise SystemExit(f"Erro: {exc}")
    print(f"Usuário criado: {conta.username!r} (perfil {conta.perfil}).")
    return 0


def _cmd_run(args) -> int:
    from . import create_app

    os.environ.setdefault("INFORMATIVO_DSN", args.dsn)
    app = create_app(dsn=args.dsn)
    if not os.environ.get("INFORMATIVO_SECRET_KEY"):
        print(
            "AVISO: INFORMATIVO_SECRET_KEY não definida — usando chave "
            "efêmera (as sessões caem a cada reinício). Defina-a em produção."
        )
    with Database(args.dsn) as db:
        init_db(db)
        total_usuarios = UsuarioRepository(db).count()
        total_fontes = FonteRepository(db).count()
    if total_usuarios == 0:
        print(
            "AVISO: nenhum usuário cadastrado. Crie o admin primeiro:\n"
            "  informativo-web create-admin --dsn " + args.dsn
        )
    print(f"Fontes cadastradas: {total_fontes}")
    print(f"Servindo em http://{args.host}:{args.port}  (DSN: {args.dsn})")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def build_parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument(
        "--dsn",
        default=os.environ.get("INFORMATIVO_DSN", DSN_PADRAO),
        help="DSN do banco SQLite (sqlite:///arquivo.db).",
    )

    p = argparse.ArgumentParser(
        prog="informativo-web",
        description="Interface web do Informativo (login, fontes e configurações).",
        parents=[comum],
    )
    sub = p.add_subparsers(dest="comando", required=True)

    pa = sub.add_parser("create-admin", help="Cria/atualiza o admin.", parents=[comum])
    pa.add_argument("--username", default="admin")
    pa.add_argument("--nome", default=None)
    pa.add_argument("--password", default=None, help="Senha (ou INFORMATIVO_ADMIN_PASSWORD).")

    pu = sub.add_parser("create-user", help="Cria um usuário.", parents=[comum])
    pu.add_argument("--username", required=True)
    pu.add_argument("--nome", default=None)
    pu.add_argument(
        "--perfil",
        required=True,
        choices=["Administrador", "Editor", "Auditor"],
    )
    pu.add_argument("--password", default=None, help="Senha (ou INFORMATIVO_USER_PASSWORD).")
    pu.add_argument("--atualizar", action="store_true", help="Atualiza se já existir.")

    pr = sub.add_parser("run", help="Sobe o servidor web.", parents=[comum])
    pr.add_argument("--host", default="127.0.0.1")
    pr.add_argument("--port", type=int, default=8000)
    pr.add_argument("--debug", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.comando == "create-admin":
        return _cmd_create_admin(args)
    if args.comando == "create-user":
        return _cmd_create_user(args)
    if args.comando == "run":
        return _cmd_run(args)
    build_parser().error(f"Comando desconhecido: {args.comando}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
