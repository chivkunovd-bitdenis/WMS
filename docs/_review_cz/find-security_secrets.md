# Ревью: security_secrets — Честный Знак (учётные данные селлера)

Диапазон: `4e82c6b..HEAD`. Scope: `seller_marking_credentials.py` (model), `seller_marking_credentials_service.py`, `marking_credentials.py` (API), `core/settings.py`, `services/integration_fernet.py`.

Общий вывод: базовая модель безопасности **в целом верная** — токены шифруются at-rest (Fernet), секреты не отдаются в API (только маска `has_*`), личный ключ ЭЦП не хранится (И7 выполнено). Но есть один значимый дефект безопасных дефолтов (ключ шифрования выводится из заведомо публичного дефолтного `jwt_secret_key` без какого-либо production-гейта) и пара меньших замечаний.

---

## 1. [HIGH] Секреты ЧЗ/СУЗ/МП по умолчанию шифруются заведомо публичным ключом (небезопасный дефолт, нет prod-гейта)

**file:line:**
- `backend/app/services/integration_fernet.py:13-19`
- `backend/app/core/settings.py:14-17, 33-37`

**Доказательство:**
```python
# integration_fernet.py
def _fernet_key_material() -> bytes:
    raw = settings.wms_secrets_fernet_key
    if raw:
        return raw.encode("utf-8")
    digest = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)
```
```python
# settings.py
jwt_secret_key: str = Field(
    default="change-me-in-production-use-long-random-secret",
    min_length=16,
)
wms_secrets_fernet_key: str | None = Field(default=None, ...)  # "dev/tests only; set explicitly in prod"
```

Когда `wms_secrets_fernet_key` не задан (дефолт `None`), ключ Fernet детерминированно выводится из `jwt_secret_key`. У `jwt_secret_key` тоже есть дефолт — публично известная строка из репозитория. Итог: при дефолтной конфигурации **все** токены ЧЗ, СУЗ/ОМS и API-ключи маркетплейсов в БД (`cz_token_enc`, `suz_oms_token_enc`, `mp_api_key_enc`) шифруются ключом, который любой может воспроизвести из исходников (`sha256("change-me-in-production-use-long-random-secret")` → urlsafe_b64). Шифрование at-rest перестаёт давать защиту: дамп БД = открытые токены.

Нигде нет проверки, что в production хотя бы один из секретов отличается от дефолта (ни в `settings.py`, ни на старте приложения). Комментарий «set explicitly in prod» — только документация, не enforcement.

**Почему важно:** токены ЧЗ/СУЗ дают доступ к чужому ЛК Честного Знака и эмиссии КМ, MP API-ключ — к кабинету маркетплейса. Это самые чувствительные секреты в фиче. Незаметная деградация шифрования при дефолтном конфиге — классический «insecure default»: выглядит зашифрованным, но не является.

**Фикс:**
- Добавить валидацию на старте: если окружение прод (`ENV`/`app_env != dev|test`), требовать явно заданный `wms_secrets_fernet_key` (и валидный `jwt_secret_key != default`), иначе `fail-fast` при инициализации Settings.
- Либо логировать критическое предупреждение и блокировать запись секретов, пока ключ дефолтный.
- Дополнительно — `min_length`/проверка валидности base64 для `wms_secrets_fernet_key` (сейчас битый ключ всплывёт только в рантайме при первом `encrypt`).

---

## 2. [LOW] Привязка ключа шифрования к `jwt_secret_key` смешивает домены секретов

**file:line:** `backend/app/services/integration_fernet.py:17-18`

**Доказательство:** ключ для шифрования данных at-rest выводится из секрета подписи JWT (`hashlib.sha256(settings.jwt_secret_key...)`).

**Почему важно:** ротация JWT-секрета (обычная операция при подозрении на компрометацию токенов сессий) молча сделает **нечитаемыми** все ранее зашифрованные токены ЧЗ/СУЗ/МП — расшифровка упадёт `InvalidToken`, интеграции встанут, и восстановить секреты будет нельзя. Связывание двух несвязанных доменов секретов опасно операционно.

**Фикс:** в проде использовать только независимый `wms_secrets_fernet_key`; деривацию из `jwt_secret_key` оставить строго для dev/test и закрыть гейтом из находки №1. В доке зафиксировать, что ротация ключа шифрования требует re-encrypt существующих строк.

---

## 3. [LOW] Расшифровка падает с `InvalidToken` без диагностируемой обёртки

**file:line:** `backend/app/services/seller_marking_credentials_service.py:237-243`, `integration_fernet.py:28`

**Доказательство:** `decrypt_secret` вызывает `get_fernet().decrypt(...)` напрямую. При смене ключа/повреждении данных летит `cryptography.fernet.InvalidToken`.

**Почему важно (для security_secrets):** само по себе не утечка — наоборот, замечание в плюс: исключение `InvalidToken` НЕ содержит plaintext и не логируется здесь (логгеров в scope нет — проверено grep'ом). Риск только в том, что необработанное исключение в `get_decrypted_credentials_for_seller` может всплыть в трейсбэке вызывающего job/HTTP-слоя; trace покажет cipher-text (`cz_token_enc`) в локальных переменных некоторых обработчиков ошибок. Cipher-text без ключа не секрет, поэтому severity низкая.

**Фикс:** обернуть `decrypt_secret` в доменную ошибку (`SecretDecryptError`) без включения исходного значения, чтобы наверняка исключить попадание шифртекста/ключа в логи трассировки на стороне вызывающего.

---

## Проверено и проблем НЕТ (подтверждение инвариантов)

- **Секреты не утекают в ответы API.** `MarkingCredentialsOut` и `MarkingCredentialsPublic` отдают только `has_cz_token/has_suz_oms_token/has_mp_api_key` (булевы маски, `service:88-90`) + `mchd_id` (идентификатор доверенности, не секрет) + настройки. Эндпоинта выдачи расшифрованных секретов в API нет; `get_decrypted_credentials_for_seller` — внутренний (для job'ов), не смонтирован в router. (`marking_credentials.py:47-76, 226-264`)
- **Шифрование at-rest применяется на записи.** `_apply_secret_patch` (`service:111-127`) всегда прогоняет непустую строку через `encrypt_secret` перед `setattr`; plaintext в колонки `*_enc` не пишется. Пустая строка → `token_empty` (422), не пустой шифртекст.
- **И7 — личный ключ ЭЦП не хранится.** В модели `SellerMarkingCredentials` нет поля под приватный ключ/контейнер: только токены доступа, `mchd_id`, `mchd_valid_until`, `signing_method` (`ff_kep_mchd`/`seller_cloud`/`manual`). Облачная подпись (`seller_cloud`) и КЭП ФФ соответствуют §8.2 дизайна. (`model:32-69`, design RU:406-424)
- **Нет логирования секретов.** В трёх файлах scope нет ни одного `log`/`print` (grep, exit=1). Plaintext токенов нигде не пишется в лог.
- **Мультитенант-изоляция секретов.** Все операции проходят `_seller_in_tenant` (`service:59-65`) — секреты чужого тенанта не читаются/не патчатся через подмену `seller_id`.
