from __future__ import annotations

import argparse
import asyncio
import logging

import uvicorn

from kitframe.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="kitframe")
    sub = parser.add_subparsers(dest="command", required=True)

    api = sub.add_parser("api")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8080)

    sub.add_parser("worker")
    sub.add_parser("seed")
    sub.add_parser("migrate")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.command == "api":
        uvicorn.run("kitframe.api.app:app", host=args.host, port=args.port, reload=get_settings().app_env == "local")
    elif args.command == "worker":
        from kitframe.jobs.worker import run_worker

        run_worker()
    elif args.command == "seed":
        from kitframe.db.seed import run_seed

        asyncio.run(run_seed(with_passwords=get_settings().seed_passwords))
    elif args.command == "migrate":
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root)


if __name__ == "__main__":
    main()
