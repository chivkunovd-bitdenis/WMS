"""python -m support_agent run | check-config"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import load_config
from .runner import build_agent, install_logging


def check_config(path: str | None) -> int:
    """Критичное (без него службе нечего делать) -> код 1; остальное — предупреждения."""
    cfg = load_config(path)
    critical, warnings = [], []
    t = cfg.telegram
    if not t.intake_token:
        critical.append("telegram.intake_bot_token не задан (бот приёма)")
    if not t.owner_token:
        critical.append("telegram.owner_bot_token не задан (бот владельца)")
    if t.intake_token and t.single_bot:
        warnings.append("токены бота приёма и бота владельца совпадают: работает один бот")
    if not t.owner_user_id or not t.owner_chat_id:
        critical.append("telegram.owner_user_id / owner_chat_id не заданы")
    if not t.chats:
        warnings.append("telegram.chats пуст: чаты добавляются командой владельца «привяжи к ИП …»")
    if not cfg.repo:
        critical.append("repo не задан")
    if not (cfg.trello.api_key and cfg.trello.token and cfg.trello.board_id):
        warnings.append("trello: нет ключа, токена или доски (карточки создаваться не будут)")
    if not cfg.wms.agent_key:
        warnings.append("wms.agent_key не задан (форма «?» не опрашивается)")
    if not (cfg.openai.api_key or os.environ.get("OPENAI_API_KEY")):
        warnings.append("openai.api_key (или OPENAI_API_KEY) не задан: голос не расшифровывается")
    if cfg.prod_db.enabled:
        key = Path(os.path.expanduser(cfg.prod_db.ssh_key_path))
        if not key.is_file():
            warnings.append(f"prod_db включён, но ключа нет: {key}")
        elif key.stat().st_mode & 0o077:
            warnings.append("ключ prod_db доступен другим пользователям (нужны права 600)")
    if not cfg.hotfix.deployed_sha_cmd:
        warnings.append("hotfix.deployed_sha_cmd не задан (хотфикс не сможет проверить версию)")
    for line in critical:
        print("ОШИБКА:", line)
    for line in warnings:
        print("Предупреждение:", line)
    if not critical and not warnings:
        print("Конфигурация заполнена.")
    return 1 if critical else 0


def check_bots(path: str | None) -> int:
    """Один getMe на каждого бота (getUpdates не вызывается, чтобы не съесть обновления)."""
    import httpx

    from .telegram import TelegramClient

    cfg = load_config(path)
    install_logging(cfg)
    http = httpx.Client()
    bots = {"intake": cfg.telegram.intake_token}
    if not cfg.telegram.single_bot:
        bots["owner"] = cfg.telegram.owner_token
    status = 0
    for name, token in bots.items():
        try:
            me = TelegramClient(token, http).get_me()
            print(f"{name}: @{me.get('username')} (id {me.get('id')})")
        except Exception as exc:
            print(f"{name}: не удалось ({type(exc).__name__})")
            status = 1
    return status


def main() -> int:
    parser = argparse.ArgumentParser(prog="support_agent")
    parser.add_argument("command", choices=["run", "check-config", "check-bots",
                                            "pause-client-replies", "approve-client-reply"])
    parser.add_argument("--config", default=None)
    parser.add_argument("--chat-id", type=int)
    parser.add_argument("--source-message-id", type=int)
    parser.add_argument("--ticket-id", type=int, action="append", default=[])
    parser.add_argument("--version")
    parser.add_argument("--text-file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "check-config":
        return check_config(args.config)
    if args.command == "check-bots":
        return check_bots(args.config)
    if args.command in {"pause-client-replies", "approve-client-reply"}:
        if args.chat_id is None or args.source_message_id is None:
            parser.error("--chat-id and --source-message-id are required")
        from .store import Store

        cfg = load_config(args.config)
        store = Store(cfg.db_path)
        try:
            if args.command == "pause-client-replies":
                store.pause_client_replies(chat_id=args.chat_id, ticket_ids=args.ticket_id,
                    owner_user_id=cfg.telegram.owner_user_id, source_message_id=args.source_message_id)
                print(f"Client replies paused for chat {args.chat_id}.")
            else:
                if len(args.ticket_id) != 1 or not args.version or args.text_file is None:
                    parser.error("one --ticket-id, --version and --text-file are required")
                key = store.approve_client_reply(chat_id=args.chat_id, ticket_id=args.ticket_id[0],
                    version=args.version, text=args.text_file.read_text(encoding="utf-8"),
                    owner_user_id=cfg.telegram.owner_user_id, owner_chat_id=cfg.telegram.owner_chat_id,
                    source_message_id=args.source_message_id)
                print(f"One specific reply queued: {key}. Chat remains paused.")
            return 0
        except ValueError as exc:
            print(f"Reply policy rejected: {exc}")
            return 1
        finally:
            store.db.close()
    build_agent(load_config(args.config)).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
