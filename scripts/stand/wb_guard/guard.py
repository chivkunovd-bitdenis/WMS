#!/usr/bin/env python3
"""Сторож между стендом и живым кабинетом Wildberries.

Владелец разрешил тестировать на своём кабинете Denmarcs, и ключ в снимке оставлен живым
намеренно. Но ночью по стенду ходят агенты, и одна кнопка «Передать в WB» означает
настоящую отгрузку в настоящем кабинете, а оприходованные остатки — обещание
маркетплейсу товара, которого нет.

Поэтому читать можно всё, а писать нельзя. Это не пожелание в промпте, которое агент
может не прочитать, а отказ на уровне сети: запрос физически не уходит.

Разрешить запись осознанно: WB_GUARD_ALLOW_WRITES=1 (владелец включает вручную, на один
прогон, и выключает обратно).
"""
from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import urllib.error
import urllib.request

ВВЕРХ = {
    "/marketplace": "https://marketplace-api.wildberries.ru",
    "/content": "https://content-api.wildberries.ru",
    "/supplies": "https://supplies-api.wildberries.ru",
}
ЧИТАЮЩИЕ = {"GET", "HEAD", "OPTIONS"}
ПУСКАТЬ_ЗАПИСЬ = os.environ.get("WB_GUARD_ALLOW_WRITES") == "1"


class Сторож(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, формат, *арг):   # noqa: N802,ANN001
        sys.stderr.write("[wb-guard] " + формат % арг + "\n")

    def _разобрать(self) -> tuple[str, str] | None:
        путь = urlparse(self.path).path
        for префикс, адрес in ВВЕРХ.items():
            if путь.startswith(префикс):
                return адрес, self.path[len(префикс):] or "/"
        return None

    def _отказ(self, код: int, текст: str) -> None:
        тело = ('{"detail":"' + текст + '"}').encode()
        self.send_response(код)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(тело)))
        self.end_headers()
        self.wfile.write(тело)

    def _проксировать(self) -> None:
        цель = self._разобрать()
        if цель is None:
            return self._отказ(404, "unknown upstream prefix")
        адрес, хвост = цель

        if self.command not in ЧИТАЮЩИЕ and not ПУСКАТЬ_ЗАПИСЬ:
            # Кричим в лог, чтобы утром было видно, кто и куда ломился.
            self.log_message("ЗАПИСЬ ЗАПРЕЩЕНА: %s %s%s", self.command, адрес, хвост)
            return self._отказ(
                403, "wb_guard_write_blocked: стенд ходит в живой кабинет только на чтение")

        длина = int(self.headers.get("Content-Length") or 0)
        тело = self.rfile.read(длина) if длина else None
        запрос = urllib.request.Request(адрес + хвост, data=тело, method=self.command)
        for имя, значение in self.headers.items():
            if имя.lower() not in {"host", "content-length", "connection"}:
                запрос.add_header(имя, значение)
        try:
            with urllib.request.urlopen(запрос, timeout=60) as ответ:
                данные = ответ.read()
                self.send_response(ответ.status)
                for имя, значение in ответ.headers.items():
                    if имя.lower() not in {"transfer-encoding", "content-length", "connection"}:
                        self.send_header(имя, значение)
                self.send_header("Content-Length", str(len(данные)))
                self.end_headers()
                self.wfile.write(данные)
        except urllib.error.HTTPError as о:
            данные = о.read()
            self.send_response(о.code)
            self.send_header("Content-Type", о.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(данные)))
            self.end_headers()
            self.wfile.write(данные)
        except Exception as е:                                   # noqa: BLE001
            self._отказ(502, f"wb_guard_upstream_error: {е}")

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _проксировать


if __name__ == "__main__":
    режим = "ЗАПИСЬ РАЗРЕШЕНА ВЛАДЕЛЬЦЕМ" if ПУСКАТЬ_ЗАПИСЬ else "только чтение"
    print(f"[wb-guard] слушаю :8000, режим: {режим}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Сторож).serve_forever()
