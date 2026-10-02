"""python -m support_agent run | check-config"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import load_config
from .runner import build_agent


def check_config(path: str | None) -> int:
    """Критичное (без него службе нечего делать) -> код 1; остальное — предупреждения."""
    cfg = load_config(path)
    critical, warnings = [], []
    t = cfg.telegram
    if not t.bot_token:
        critical.append("telegram.bot_token не задан")
    if not t.owner_user_id or not t.owner_chat_id:
        critical.append("telegram.owner_user_id / owner_chat_id не заданы")
    if not t.chats:
        critical.append("telegram.chats пуст (нет обслуживаемых чатов)")
    if not cfg.repo:
        critical.append("repo не задан")
    if not (cfg.trello.api_key and cfg.trello.token and cfg.trello.board_id):
        warnings.append("trello: нет ключа, токена или доски (карточки создаваться не будут)")
    if not cfg.wms.agent_key:
        warnings.append("wms.agent_key не задан (форма «?» не опрашивается)")
    if not (cfg.openai.api_key or os.environ.get("OPENAI_API_KEY")):
        warnings.append("openai.api_key (или OPENAI_API_KEY) не задан: голос не расшифровывается")
    if not cfg.hotfix.deployed_sha_cmd:
        warnings.append("hotfix.deployed_sha_cmd не задан (хотфикс не сможет проверить версию)")
    for line in critical:
        print("ОШИБКА:", line)
    for line in warnings:
        print("Предупреждение:", line)
    if not critical and not warnings:
        print("Конфигурация заполнена.")
    return 1 if critical else 0


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
