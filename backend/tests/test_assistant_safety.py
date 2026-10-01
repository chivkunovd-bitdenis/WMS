"""WMS-433: фильтр технических подробностей — вторая (defence-in-depth)

копия того же кода живёт в ``tools/assistant-agent/wms_assistant_agent.py``
(её тесты — класс ``SafetyFilterTest`` в
``tools/assistant-agent/test_wms_assistant_agent.py``) и должна быть
поведенчески синхронна с ``app/services/assistant_safety.py`` (текстуально —
кроме источника списка внутренних имён, см. докстринг обоих модулей).
Этот файл проверяет ИМЕННО серверную копию тем же набором случаев, чтобы обе
копии были покрыты тестами одинаково, а не только исполнительская.
``TestBothCopiesAgree`` ниже прогоняет ОДИН И ТОТ ЖЕ набор входов через ОБЕ
копии и сравнивает результат (ревью Astra круг 4, требование «г»).

Ревью Astra круг 3, дефект №26: старое правило пропускало многострочный код
без скобок/присваивания и ложно блокировало обычную лексику интерфейса
(«таблица FBS», «поле SKU»).

Ревью Astra круг 4, дефект №33: то же самое правило по-прежнему ловилось на
конкретных примерах, а не на принципе — пять новых обходов (пропуск отступа
после ``strip()``, пустая строка/комментарий между строками кода, обычные
кавычки вместо обратных, имя таблицы без ``_``/CamelCase) и один ложный отказ
(«FBS» в обратных кавычках). Реальный вход к ревьюеру шёл через
``sanitize_answer``/``submit_executor_result``, поэтому тесты здесь тоже идут
через ``sanitize_answer``, а не только через ``contains_unsafe_content``.

Ревью Astra круг 5, дефект №35: правило «≥2 строк или 1 строка с отступом ≥4»
по-прежнему пропускало одиночную строку без окружения («import os»,
«print("hello")», «answer = 42»), код под маркером списка («- import os») и
код-фрагмент внутри предложения («Вот код: import os; print(os.getcwd())»).
Тем же кругом ведущий (не само ревью) нашёл обратную проблему: 15 коротких
слов без «_»/CamelCase в списке внутренних имён оказались обычной лексикой
ответа («Login на портале селлера» блокировался) — см.
``TestCommonShortWordsAreNotFalselyBlocked`` ниже. Из-за этого решение круга 4
про голое «users» (без «_») **сменилось на противоположное**: раньше оно
обязано было блокироваться (см. старую версию ``_MUST_BLOCK`` до круга 5),
теперь — обязано проходить, как обычное слово языка.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from app.services.assistant_safety import (
    _INTERNAL_IDENTIFIERS,
    SAFE_REPLACEMENT_TEXT,
    _load_frontend_identifiers,
    _load_frontend_identifiers_snapshot,
    contains_unsafe_content,
    sanitize_answer,
)

# Обязательный набор ревью (см. astra-review-round4.md, раздел «Что
# проверено и совпало»): восемь дополнительных положительных фраз по
# реальным строкам интерфейса плюс обязательные примеры кругов 1-4.
_MUST_PASS = (
    "Откройте `Создать` (кнопка справа).",
    "Заполните поле SKU в карточке товара.",
    "В таблице FBS выберите заказ и откройте поставку.",
    "В таблице `FBS` выберите заказ и откройте поставку.",
    "Создать поставку",
    "Синхронизировать заказы",
    "Печать всех QR",
    "Артикул продавца",
    "Скачать Excel",
    "Маршрут сдачи",
    "WB nmID",
    "Откройте таблицу заказов и найдите нужную поставку.",
    "Перейдите в раздел Маршрут сдачи и укажите склад WB.",
    "Нажмите кнопку Создать поставку в разделе FBS.",
    # 10 реалистичных ответов модели (по образцу реальных answer_text из
    # прогонов этой сессии и реальной лексики фронта FBS-поставок:
    # frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx, FbsSupplyCreateDialog.tsx,
    # FfFbsPickList.tsx, FfProductsCatalogScreen.tsx).
    "Вы уже на нужном экране — «Инвентаризация». "
    "Нажмите кнопку **«Создать»** в правом верхнем углу.",
    "Это не ваша ошибка — сервер временно не смог обработать запрос. "
    "Документ ИНВ-000551 по-прежнему в статусе «Черновик».",
    "Зайдите в раздел Инвентаризация и нажмите Создать.",
    "Поставка ИНВ-000124 ещё не завершена.",
    "Откройте раздел «Поставки WB» и выберите нужную дату отгрузки.",
    "Нажмите «Печать этикеток», чтобы распечатать стикеры для короба.",
    "В карточке товара укажите штрихкод и сохраните изменения.",
    "Перейдите в раздел «Остатки» и найдите нужный SKU через поиск.",
    "Сначала подтвердите приёмку, а затем система предложит распределить товар по ячейкам.",
    "Маршрут сдачи для этой поставки ещё не выбран — откройте карточку поставки и укажите его.",
    # круг 5: позитивный корпус к дефекту №35 (числа/присваивание кириллицей/
    # двоеточие в обычной фразе не должны трактоваться как код-сегмент).
    "Итого: 42 шт.",
    "Скидка = 10 %",
    "Нажмите Excel → Скачать",
    "Email: ivan@example.com — это поле сотрудника",
    # круг 5: находка ведущего — короткие слова без "_"/CamelCase не должны
    # резаться только за совпадение с реальным (но обычным) именем.
    "Login на портале селлера",
    "Просмотр Health системы",
    "Статус: users не найден",
    # круг 8 (переоткрытый C13, требование 4 ведущего): короткие фразы с
    # обычной лексикой интерфейса, которые могли бы случайно совпасть с
    # именем legacy-компонента фронта (frontend/src/ui/*.tsx) — "FBS"/"Excel"
    # сами по себе НЕ определены в frontend/src (это аббревиатура и сторонний
    # формат файла), поэтому не должны попасть в список внутренних имён.
    "таблица FBS",
    "кнопка Excel",
)

_MUST_BLOCK = (
    # круг 1
    "Вот код:\n```python\ndef f(): pass\n```",
    "Смотрите backend/app/services/fbs_print_job_service.py",
    "SELECT * FROM users WHERE id = 1",
    "SELECT\n id,\n email\nFROM users",
    "Вот пример:\n\n    def post_supply():\n        return True",
    "Таблица assistant_messages; функция submit_executor_result",
    "sk-" + "​".join(list("abcd1234efgh5678")),
    # круг 2
    "Вот пример:\n\n    total = 1\n    enabled = True",
    "Таблица `assistant_messages`",
    # круг 3
    "Смотри:\n\n    import os\n    import sys\n",
    "    if ready:\n        return True\n",
    # круг 4 — пять новых обходов, дефект №33
    "    import os\n    import sys",
    "Вот пример:\n\n    total = 1\n\n    enabled = True",
    "Вот пример:\n\n    def post_supply():\n        # сохранить результат\n        return True",
    'Таблица "assistant_messages", функция \'submit_executor_result\'',
    # круг 5: «Таблица users хранит пользователей.» ушла из этого списка —
    # решение круга 4 сменилось на противоположное, см. docstring модуля и
    # TestCommonShortWordsAreNotFalselyBlocked. Здесь — замена, которая
    # проверяет тот же принцип (имя без "_"/CamelCase всё ещё ловится, если
    # оно НЕ короткое обычное слово): "autherror" — реальное имя (9 символов,
    # длиннее порога в 6 и не входит в allowlist круга 5).
    "Класс autherror описывает исключение.",
    # найдено ведущим после круга 4: распространённые форматы токенов,
    # которых не было в старых шаблонах (см. TestSecretTokenFormats выше) —
    # добавлены и сюда, чтобы TestBothCopiesAgree тоже прогнал их через обе
    # копии фильтра.
    "ghp_" + "A" * 36,
    "gho_" + "B" * 36,
    "ghu_" + "C" * 36,
    "ghs_" + "D" * 36,
    "github_pat_" + "E" * 20,
    "xoxb-" "1234567890-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx",
    "AIza" + "S" * 35,
    "ya29." + "T" * 20,
    "-----BEGIN RSA PRIVATE KEY-----",
    "sk-ant-api03-" + "A1b2C3d4" * 3,
    # круг 5, дефект №35: одиночная строка без отступа/окружения, код под
    # маркером списка, код-фрагмент внутри предложения.
    "import os",
    'print("hello")',
    "answer = 42",
    "- import os\n- import sys",
    "Вот код: import os; print(os.getcwd())",
    # круг 8 (переоткрытый C13): реальные имена фронтовых компонентов
    # работающей версии (frontend/src/screens/ff/FfInventoryListScreen.tsx,
    # frontend/src/layouts/AuthedAppLayout.tsx,
    # frontend/src/components/assistant/AssistantPanel.tsx) — по решению
    # аналитика (R17, 4.3) жёсткий класс, не должны проходить к пользователю
    # ни в каком контексте предложения.
    "Откройте FfInventoryListScreen",
    "В AuthedAppLayout кнопка",
    "компонент AssistantPanel",
)


class TestSanitizeAnswerMustPass:
    """Ревью Astra круг 4, требование «е»: тестируем именно sanitize_answer

    (реальный путь текста модели), а не только contains_unsafe_content.
    """

    def test_all_required_positive_phrases_pass_unchanged(self) -> None:
        failures = [t for t in _MUST_PASS if sanitize_answer(t) != t.strip()]
        assert not failures, f"ложно заблокированы: {failures!r}"


class TestSanitizeAnswerMustBlock:
    def test_all_required_negative_inputs_are_replaced(self) -> None:
        failures = [t for t in _MUST_BLOCK if sanitize_answer(t) != SAFE_REPLACEMENT_TEXT]
        assert not failures, f"пропущены как безопасные: {failures!r}"


class TestSecretTokenFormats:
    """Найдено ведущим при финальной проверке круга 4 (не самим ревью Astra):

    старые шаблоны ``sk-...``/``AKIA...``/JWT/длинная base64-строка ловили
    ключи Anthropic, OpenAI, AWS и JWT, но пропускали токены других
    провайдеров с собственным префиксом — воспроизведено:
    ``sanitize_answer("ghp_" + "A" * 36)`` возвращал текст как есть.
    Причина — подчёркивание внутри префикса разрывает подряд идущие
    [A-Za-z0-9+/] короче порога универсального «длинная строка» шаблона.
    """

    def test_github_personal_access_token_is_unsafe(self):
        assert sanitize_answer("ghp_" + "A" * 36) == SAFE_REPLACEMENT_TEXT

    def test_other_github_token_prefixes_are_unsafe(self):
        assert sanitize_answer("gho_" + "B" * 36) == SAFE_REPLACEMENT_TEXT
        assert sanitize_answer("ghu_" + "C" * 36) == SAFE_REPLACEMENT_TEXT
        assert sanitize_answer("ghs_" + "D" * 36) == SAFE_REPLACEMENT_TEXT
        assert sanitize_answer("github_pat_" + "E" * 20) == SAFE_REPLACEMENT_TEXT

    def test_slack_token_is_unsafe(self):
        text = "xoxb-" "1234567890-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT

    def test_google_api_key_is_unsafe(self):
        assert sanitize_answer("AIza" + "S" * 35) == SAFE_REPLACEMENT_TEXT

    def test_google_oauth_token_is_unsafe(self):
        assert sanitize_answer("ya29." + "T" * 20) == SAFE_REPLACEMENT_TEXT

    def test_private_key_header_is_unsafe(self):
        assert sanitize_answer("-----BEGIN RSA PRIVATE KEY-----") == SAFE_REPLACEMENT_TEXT
        assert sanitize_answer("-----BEGIN PRIVATE KEY-----") == SAFE_REPLACEMENT_TEXT

    def test_anthropic_key_with_hyphens_is_unsafe(self):
        text = "sk-ant-api03-" + "A1b2C3d4" * 3
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT


class TestContainsUnsafeContentDefect33FiveBypasses:
    """Каждый из пяти обходов круга 4 — отдельным тестом с объяснением."""

    def test_leading_line_indent_is_not_lost_to_outer_strip(self) -> None:
        # п.1: sanitize_answer раньше делал strip() ДО проверки — терялся
        # отступ ПЕРВОЙ строки. Теперь проверка — на исходном тексте, и
        # правило (б) вообще не требует отступа для import/from.
        assert sanitize_answer("    import os\n    import sys") == SAFE_REPLACEMENT_TEXT

    def test_blank_line_between_code_lines_does_not_reset_the_count(self) -> None:
        text = "Вот пример:\n\n    total = 1\n\n    enabled = True"
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT

    def test_comment_between_code_lines_does_not_reset_the_count(self) -> None:
        text = (
            "Вот пример:\n\n    def post_supply():\n"
            "        # сохранить результат\n        return True"
        )
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT

    def test_regular_quotes_around_identifier_are_caught_same_as_backticks(self) -> None:
        text = 'Таблица "assistant_messages", функция \'submit_executor_result\''
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT

    def test_identifier_without_underscore_or_case_change_is_caught(self) -> None:
        # Круг 5 заменил пример: «Таблица users хранит пользователей.»
        # раньше была обязана блокироваться, теперь ОБЯЗАНА проходить —
        # «users» короткое (≤6 символов) и попало в allowlist круга 5 (см.
        # TestCommonShortWordsAreNotFalselyBlocked). Принцип «имя без "_" и
        # без CamelCase всё равно ловится» по-прежнему верен для имён ДЛИННЕЕ
        # порога и не из allowlist — "autherror" (9 символов) это показывает.
        assert sanitize_answer("Класс autherror описывает исключение.") == SAFE_REPLACEMENT_TEXT

    def test_fbs_in_backticks_is_no_longer_a_false_rejection(self) -> None:
        # Обратная ошибка круга 4: «FBS» не входит в список настоящих
        # внутренних имён ни при каком оформлении кавычек.
        text = "В таблице `FBS` выберите заказ и откройте поставку."
        assert sanitize_answer(text) == text


class TestDefect35SingleLineCodeWithoutIndent:
    """Круг 5, дефект №35: одиночная строка без окружения и без отступа,

    код под маркером списка, код-фрагмент внутри предложения — каждый вход
    отдельным тестом с объяснением, какой именно сильный признак сработал.
    """

    def test_bare_import_without_surrounding_lines_or_indent(self) -> None:
        assert sanitize_answer("import os") == SAFE_REPLACEMENT_TEXT

    def test_bare_call_with_quoted_argument(self) -> None:
        assert sanitize_answer('print("hello")') == SAFE_REPLACEMENT_TEXT

    def test_bare_latin_assignment_without_indent(self) -> None:
        assert sanitize_answer("answer = 42") == SAFE_REPLACEMENT_TEXT

    def test_code_under_list_markers(self) -> None:
        # Маркер списка («- ») раньше мешал строке начинаться с "import" —
        # теперь маркер снимается перед проверкой.
        assert sanitize_answer("- import os\n- import sys") == SAFE_REPLACEMENT_TEXT

    def test_code_fragment_inside_a_sentence_split_by_colon_and_semicolon(self) -> None:
        text = "Вот код: import os; print(os.getcwd())"
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT

    def test_dotted_call_without_quotes_is_still_strong(self) -> None:
        # os.getcwd() — точка в цепочке перед скобками, без кавычек внутри.
        assert sanitize_answer("os.getcwd()") == SAFE_REPLACEMENT_TEXT

    def test_positive_corpus_with_colon_or_equals_is_not_cut(self) -> None:
        # Двоеточие/присваивание сами по себе не код — нужен ещё и сильный
        # признак сегмента (import/call-с-точкой-или-кавычкой/и т.п.).
        assert sanitize_answer("Итого: 42 шт.") == "Итого: 42 шт."
        assert sanitize_answer("Скидка = 10 %") == "Скидка = 10 %"
        text = "Email: ivan@example.com — это поле сотрудника"
        assert sanitize_answer(text) == text


class TestCommonShortWordsAreNotFalselyBlocked:
    """Круг 5: находка ведущего (не самого ревью Astra) — 15 коротких слов

    без "_"/CamelCase в списке из 3412 внутренних имён оказались обычной
    лексикой ответа: «Login на портале селлера» и «Просмотр Health системы»
    блокировались. Имена с подчёркиванием (assistant_messages,
    submit_executor_result) исключение не затрагивает — они блокируются как
    раньше.
    """

    def test_login_as_plain_word_passes(self) -> None:
        text = "Login на портале селлера"
        assert sanitize_answer(text) == text

    def test_health_as_plain_word_passes(self) -> None:
        text = "Просмотр Health системы"
        assert sanitize_answer(text) == text

    def test_users_as_plain_word_passes_even_after_colon(self) -> None:
        # users — реальное имя таблицы, но короткое обычное слово: пропускать.
        text = "Статус: users не найден"
        assert sanitize_answer(text) == text

    def test_underscored_identifiers_still_blocked(self) -> None:
        text = "Таблица assistant_messages; функция submit_executor_result"
        assert sanitize_answer(text) == SAFE_REPLACEMENT_TEXT

    def test_reported_words_are_absent_from_the_real_identifier_list(self) -> None:
        reported = {
            "call", "delta", "fetch", "has", "http", "login", "me", "net",
            "now", "one", "users", "wait", "health", "status", "products",
        }
        assert not (reported & _INTERNAL_IDENTIFIERS)

    def test_underscored_real_names_are_still_in_the_list(self) -> None:
        assert "assistant_messages" in _INTERNAL_IDENTIFIERS
        assert "submit_executor_result" in _INTERNAL_IDENTIFIERS


class TestIdentifierShapedButNotRealWordPasses:
    """Дефект №33, принцип «а»: замена эвристики «похоже на идентификатор»

    точным списком реальных имён — намеренное следствие: слово, которое
    выглядит как идентификатор, но не является настоящим внутренним именем,
    само по себе больше не признак утечки.
    """

    def test_fictional_snake_case_or_camel_case_word_is_safe(self) -> None:
        assert not contains_unsafe_content("Таблица table_products_sku хранит остатки.")
        assert not contains_unsafe_content("Функция calculateStockLimit считает остаток.")
        assert not contains_unsafe_content("Переменная `assembling_status` управляет переходом.")

    def test_no_required_positive_word_collides_with_a_real_identifier(self) -> None:
        # Факт, а не догадка (ревью Astra круг 4: «составь короткий allowlist
        # по факту пересечений, если такие есть — проверь»): полный список
        # реальных внутренних имён сверен со всеми словами обязательного
        # положительного набора — пересечений нет, поэтому
        # ``_IDENTIFIER_ALLOWLIST`` в assistant_safety.py пуст.
        required_words = {"sku", "fbs", "qr", "excel", "wb", "nmid"}
        assert not (required_words & _INTERNAL_IDENTIFIERS)


class TestBothCopiesAgree:
    """Ревью Astra круг 4, требование «г»: один общий модуль-источник правды

    для обеих копий недостижим (исполнитель — отдельный процесс без
    backend/app под рукой в общем случае), поэтому вместо этого гоняем ОДИН И
    ТОТ ЖЕ набор входов через ОБЕ копии и сравниваем результат — чтобы
    расхождение (как в этом самом круге ревью) ловилось тестом, а не только
    ручным прогоном.
    """

    @staticmethod
    def _executor_module() -> ModuleType:
        tools_dir = Path(__file__).resolve().parents[2] / "tools" / "assistant-agent"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        import wms_assistant_agent as executor  # type: ignore[import-not-found]

        module: ModuleType = executor
        return module

    def test_same_verdict_for_full_corpus_using_the_same_real_identifiers(self) -> None:
        executor = self._executor_module()
        # Круг 8 (переоткрытый C13): обе копии теперь объединяют backend/app
        # с именами frontend/src. Исполнитель сканирует frontend/src живьём
        # (он получает свежий git checkout нужной версии на каждый запрос);
        # бэкенд не может — его Docker-образ не содержит frontend/src, поэтому
        # он использует закоммиченный снимок (``_load_frontend_identifiers_snapshot``
        # в assistant_safety.py). На ЭТОМ состоянии репозитория (общий рабочий
        # каталог — тот же git checkout, что видят обе копии) оба объединённых
        # множества обязаны совпадать; расхождение означало бы, что снимок
        # отстал от frontend/src (за этим отдельно следит
        # TestFrontendIdentifierSnapshotIsFresh — она ловит именно устаревание
        # снимка, а не поведенческое расхождение, которое проверяется здесь).
        repo_root = Path(__file__).resolve().parents[2]
        executor_identifiers = executor._get_internal_identifiers(
            repo_root, "local-test", used_fallback=True
        )
        assert executor_identifiers == _INTERNAL_IDENTIFIERS

        mismatches = []
        for text in (*_MUST_PASS, *_MUST_BLOCK):
            backend_blocked = sanitize_answer(text) == SAFE_REPLACEMENT_TEXT
            executor_result = executor.sanitize_answer(text, executor_identifiers)
            executor_blocked = executor_result == executor.SAFE_REPLACEMENT_TEXT
            if backend_blocked != executor_blocked:
                mismatches.append((text, backend_blocked, executor_blocked))
        assert not mismatches, f"копии разошлись: {mismatches!r}"


class TestFrontendIdentifierSnapshotIsFresh:
    """Круг 8 (переоткрытый C13, требование 3 ведущего): снимок

    ``assistant_frontend_identifiers.txt`` — закоммиченная копия результата
    сканирования ``frontend/src`` (Docker-образ API не включает frontend/src,
    поэтому живой скан при импорте недоступен бэкенду, в отличие от
    backend/app). Если кто-то добавит/переименует компонент во фронте и
    забудет перегенерировать снимок (``python -m app.services.assistant_safety
    --refresh``), этот тест должен упасть в CI — иначе новое имя молча
    перестанет распознаваться бэкенд-копией фильтра как жёсткий класс R17.
    """

    def test_snapshot_matches_a_fresh_scan_of_frontend_src(self) -> None:
        frontend_src = Path(__file__).resolve().parents[2] / "frontend" / "src"
        assert frontend_src.is_dir(), f"frontend/src не найден по пути {frontend_src}"
        fresh = _load_frontend_identifiers(frontend_src)
        snapshot = _load_frontend_identifiers_snapshot()
        assert fresh == snapshot, (
            "снимок assistant_frontend_identifiers.txt устарел — запусти "
            "`python -m app.services.assistant_safety --refresh` из backend/ и закоммить файл. "
            f"новые: {sorted(fresh - snapshot)!r}; удалённые: {sorted(snapshot - fresh)!r}"
        )
