"""Поиск селлеров и подготовка доступа через шлюз на сервере (WMS-641 R39-R41), без модели.

Всё идёт по тому же ssh-ключу и той же forced command, что и запросы аналитиков: шлюз принимает только
`find-seller <строка>` и `ensure-seller <uuid>`. Название ищется доверенным кодом; строка проверяется до
отправки (шлюз проверяет её ещё раз) и в SQL не попадает как текст: это переменная psql."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from .prod_sql import SELLER_RE, ProdSqlSettings, Runner, default_runner, ssh_argv

NAME_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё .,'\"«»()+&/_-]{2,80}$")
PREFIX_RE = re.compile(r"^(?:ип|ip|и\.\s?п\.|индивидуальный предприниматель)\s+", re.IGNORECASE)


class DirectoryError(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    seller_id: str
    seller_name: str
    tenant_id: str
    tenant_name: str


@dataclass(frozen=True)
class TenantCandidate:
    tenant_id: str
    tenant_name: str
    sellers: int


def clean_tenant_name(raw: str) -> str:
    """Название фулфилмента без слова «ФФ»/«фулфилмент» и кавычек по краям."""
    name = " ".join(raw.replace("«", "").replace("»", "").strip(" \"'.,").split())
    return re.sub(r"^(?:фулфилмент\w*|фф)\s+", "", name, flags=re.IGNORECASE).strip()


def clean_name(raw: str) -> str:
    """Название без префикса «ИП»/«IP» (расшифровка может дать «IP») и без кавычек по краям."""
    name = " ".join(raw.replace("«", "").replace("»", "").strip(" \"'.,").split())
    name = PREFIX_RE.sub("", name).strip()
    return name


class SellerDirectory:
    def __init__(self, cfg: ProdSqlSettings, runner: Runner = default_runner) -> None:
        self.cfg, self.runner = cfg, runner

    def _call(self, command: str) -> str:
        rc, out, err = self.runner(ssh_argv(self.cfg, command), "", self.cfg.timeout_sec)
        if rc != 0:
            raise DirectoryError(f"шлюз ответил кодом {rc}: {(err or out).strip()[:200]}")
        return out

    def find(self, raw_name: str) -> list[Candidate]:
        name = clean_name(raw_name)
        if not NAME_RE.match(name):
            raise DirectoryError("некорректное название для поиска")
        rows = list(csv.DictReader(io.StringIO(self._call(f"find-seller {name}"))))
        found = []
        for row in rows[:5]:
            if not SELLER_RE.match(row.get("seller_id", "")):
                raise DirectoryError("шлюз вернул некорректный идентификатор")
            found.append(Candidate(row["seller_id"], row.get("seller_name", ""), row.get("tenant_id", ""),
                                   row.get("tenant_name", "")))
        return found

    def find_tenants(self, raw_name: str) -> list[TenantCandidate]:
        name = clean_tenant_name(raw_name)
        if not NAME_RE.match(name):
            raise DirectoryError("некорректное название для поиска")
        rows = list(csv.DictReader(io.StringIO(self._call(f"find-tenant {name}"))))
        found = []
        for row in rows[:5]:
            if not SELLER_RE.match(row.get("tenant_id", "")):
                raise DirectoryError("шлюз вернул некорректный идентификатор")
            try:
                count = int(row.get("sellers") or 0)
            except ValueError:
                raise DirectoryError("шлюз вернул некорректное число селлеров") from None
            found.append(TenantCandidate(row["tenant_id"], row.get("tenant_name", ""), count))
        return found

    def ensure_tenant(self, tenant_id: str) -> None:
        if not SELLER_RE.match(tenant_id):
            raise DirectoryError("некорректный идентификатор фулфилмента")
        out = self._call(f"ensure-tenant {tenant_id}")
        if not out.startswith("ok role="):
            raise DirectoryError("доступ не подготовлен: " + out.strip()[:200])

    def ensure_scope(self, level: str, scope_id: str) -> None:
        (self.ensure_tenant if level == "tenant" else self.ensure)(scope_id)

    def ensure(self, seller_id: str) -> None:
        if not SELLER_RE.match(seller_id):
            raise DirectoryError("некорректный идентификатор селлера")
        out = self._call(f"ensure-seller {seller_id}")
        if not out.startswith("ok role="):
            raise DirectoryError("доступ не подготовлен: " + out.strip()[:200])
