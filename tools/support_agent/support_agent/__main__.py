"""python -m support_agent run | check-config"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .runner import build_agent


def check_config(path: str | None) -> int:
    cfg = load_config(path)
    problems = []
    t = cfg.telegram
    if not t.bot_token:
        problems.append("telegram.bot_token не задан")
    if not t.owner_user_id or not t.owner_chat_id:
        problems.append("telegram.owner_user_id / owner_chat_id не заданы")
    if not t.chats:
        problems.append("telegram.chats пуст (нет обслуживаемых чатов)")
    if not (cfg.trello.api_key and cfg.trello.token and cfg.trello.board_id):
        problems.append("trello: нет ключа, токена или доски (карточки создаваться не будут)")
    if not cfg.wms.agent_key:
        problems.append("wms.agent_key не задан (форма «?» не опрашивается)")
    if not cfg.repo:
        problems.append("repo не задан")
    for line in problems or ["Конфигурация заполнена."]:
        print(line)
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="support_agent")
    parser.add_argument("command", choices=["run", "check-config"])
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "check-config":
        return check_config(args.config)
    build_agent(load_config(args.config)).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
