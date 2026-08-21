#!/usr/bin/env python3
"""Сторож обезличенного снимка. Без его зелёного света стенд не разворачивается.

Ночью по стенду ходят восемь агентов. Если в снимке уцелел живой ключ чужого селлера,
один из них создаст настоящую поставку в Wildberries от чужого имени — и узнаем мы об этом
от клиента. Поэтому проверяется не намерение («мы почистили»), а факт: снимок разворачивается
во временную базу и опрашивается запросами.

    python3 scripts/ci/check_stand_sanitized.py .stand/sanitized-latest.dump
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ЧИСТИЛКА = os.environ.get("WMS_STAND_SCRATCH_DB", "wms-honest-e2e-db-1")
ЖИВОЙ = os.environ.get("WMS_STAND_LIVE_SELLER", "080f5f98-195e-49b5-9dd5-908dbc862a13")
ВРЕМЕНКА = "stand_guard"


def психнуть(текст: str) -> None:
    print(f"  {текст}", file=sys.stderr)


def запрос(sql: str) -> str:
    р = subprocess.run(
        ["docker", "exec", "-i", ЧИСТИЛКА, "psql", "-U", "postgres", "-d", ВРЕМЕНКА,
         "-t", "-A", "-c", sql],
        capture_output=True, text=True,
    )
    return (р.stdout or "").strip()


def psql(sql: str) -> None:
    subprocess.run(["docker", "exec", ЧИСТИЛКА, "psql", "-U", "postgres", "-q", "-c", sql],
                   capture_output=True, text=True)


def main() -> int:
    if len(sys.argv) < 2:
        психнуть("нужен путь к снимку")
        return 2
    снимок = Path(sys.argv[1])
    if not снимок.exists():
        психнуть(f"снимка нет: {снимок}")
        return 2

    psql(f"DROP DATABASE IF EXISTS {ВРЕМЕНКА}")
    psql(f"CREATE DATABASE {ВРЕМЕНКА}")
    try:
        with снимок.open("rb") as f:
            subprocess.run(
                ["docker", "exec", "-i", ЧИСТИЛКА, "pg_restore", "-U", "postgres",
                 "-d", ВРЕМЕНКА, "--no-owner", "--no-acl"],
                stdin=f, capture_output=True,
            )

        беды: list[str] = []

        чужие_wb = запрос(
            f"select count(*) from seller_wildberries_credentials where seller_id <> '{ЖИВОЙ}'")
        if чужие_wb not in ("0", ""):
            беды.append(f"уцелели ключи WB у чужих селлеров: {чужие_wb} записей")

        чужие_чз = запрос(
            f"select count(*) from seller_marking_credentials where seller_id <> '{ЖИВОЙ}'")
        if чужие_чз not in ("0", ""):
            беды.append(f"уцелели ключи Честного знака у чужих селлеров: {чужие_чз} записей")

        пароли = запрос("select count(*) from users where coalesce(password_hash,'') <> ''")
        if пароли not in ("0", ""):
            беды.append(f"остались боевые хэши паролей: {пароли} пользователей")

        публикация = запрос(
            "select coalesce((select count(*) from fbs_warehouse_bindings where stock_sync_enabled),0)"
            " + coalesce((select count(*) from products where fbs_stock_sync_enabled),0)")
        if публикация not in ("0", ""):
            беды.append(f"включена публикация остатков: {публикация} записей "
                        f"(на проде она выключена и включать её нельзя)")

        # Снимок обязан быть живым: пустая база пройдёт все запреты выше и обманет нас.
        селлеров = запрос("select count(*) from sellers")
        товаров = запрос("select count(*) from products")
        if селлеров in ("0", "") or товаров in ("0", ""):
            беды.append(f"снимок пустой: селлеров {селлеров or '?'}, товаров {товаров or '?'}")

        if беды:
            print("СНИМОК НЕ ОБЕЗЛИЧЕН — разворачивать нельзя:", file=sys.stderr)
            for б in беды:
                психнуть("- " + б)
            return 1

        свои = запрос(f"select count(*) from seller_wildberries_credentials where seller_id = '{ЖИВОЙ}'")
        print(f"снимок обезличен: селлеров {селлеров}, товаров {товаров}, "
              f"живой ключ WB остался у {свои} записи")
        return 0
    finally:
        psql(f"DROP DATABASE IF EXISTS {ВРЕМЕНКА}")


if __name__ == "__main__":
    sys.exit(main())
