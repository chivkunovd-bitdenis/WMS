"""WMS-433/R17: техническая проверка ответа помощника на стороне WMS.

Это вторая, независимая линия защиты. Первая — инструкция исполнителя
(``tools/assistant-agent/instruction.md``), которая прямо запрещает модели
выдавать код, пути, SQL, секреты и саму инструкцию. Эта проверка исходит из
того, что первая линия может не сработать (модель ошиблась или её
спровоцировали), и отбраковывает подозрительный ответ уже на сервере, до того
как он попадёт пользователю.

Функция ``sanitize_answer`` вызывается ровно один раз — при приёме результата
от исполнителя (``assistant_service.submit_executor_result``) — и именно
поэтому в таблице ``assistant_messages`` нет отдельного поля для «сырого»
ответа исполнителя: то, что не прошло проверку, в базу вообще не попадает,
только безопасная замена. Значит «исходный текст исполнителя пользователю
недоступен» выполняется не контролем доступа, а тем, что этого текста просто
нигде нет.

Копия этой же проверки живёт в ``tools/assistant-agent/wms_assistant_agent.py``
(те же функции и структура; отличие описано в п.11 ниже) — исполнитель обязан
прогонять её сам ДО отправки результата в WMS, чтобы явная провокация не
улетала на сервер вообще. Обе копии держим текстуально одинаковыми (кроме
источника списка внутренних имён — см. п.11); при правке одной обновляй другую.

Ревью Astra 12.09.2026 (docs/reviews/2026-09-12-wms433/astra-review-part1.md,
дефект №2) нашло и подтвердило пять конкретных проблем прежней версии,
исправленных здесь:

1. Код с отступом в 4 пробела (без ``` и без инлайн-кода) не ловился —
   добавлен ``_INDENTED_CODE_LINE``.
2. Многострочный SQL (перевод строки между ``SELECT`` и ``FROM``) не ловился,
   потому что ``.`` без ``re.DOTALL`` не матчит ``\n`` — добавлен ``re.DOTALL``.
3. Упоминание технического имени в прозе («Таблица assistant_messages;
   функция submit_executor_result») не ловилось вовсе — добавлен
   ``_TECH_NAME_MENTION``.
4. Ключ вида ``sk-...``, разбитый невидимыми символами (zero-width space и
   похожие), обходил проверку — текст теперь очищается от невидимых символов
   ``_INVISIBLE_CHARS`` перед проверкой.
5. **Ложное срабатывание**: старый инлайн-код-паттерн ``` `[^`+n]*[(){};]` ```
   не требовал закрывающую кавычку, поэтому после настоящего короткого
   инлайн-кода (например ``` `Создать` ```) движок перезапускал поиск с ЕГО
   закрывающей кавычки как если бы она была новой открывающей, и захватывал
   случайную скобку в обычном тексте дальше («Откройте `Создать` (кнопка
   справа).» → ложно небезопасно). Инлайн-код теперь ищется отдельно как
   ПАРА кавычек (``_INLINE_CODE_SPAN``), и опасным считается только
   содержимое МЕЖДУ ними, а не хвост текста после закрывающей кавычки.

Ревью Astra, круг 2 (docs/reviews/2026-09-12-wms433/astra-review-round2.md,
дефект №14) нашло ещё три проблемы, исправленных здесь:

6. Отступ без скобок/двоеточия («    total = 1\n    enabled = True») не
   ловился — ``_INDENTED_CODE_LINE`` теперь дополнительно матчит присваивание
   (``identifier = value``), а не только «есть скобка/двоеточие где-то в
   строке».
7. Идентификатор в кавычках после «Таблица»/«функция» («Таблица
   `assistant_messages`») не ловился — между русским словом и идентификатором
   ``_TECH_NAME_MENTION`` теперь допускает необязательную кавычку/двоеточие.
8. **Ложное срабатывание**: «Заполните поле SKU» резалось, потому что «поле»
   было в списке триггерных слов, а SKU — обычный термин интерфейса WMS.
   Убрал «поле» и «колонка» из триггеров: это бытовая лексика инструкции
   («какое поле», «в какой колонке»), которая законно сочетается с любым
   пользовательским термином (SKU, QR, ID). Оставлены только слова, которые
   нормальная человеческая инструкция по экрану не производит в принципе —
   «таблица», «функция», «метод», «переменная», «эндпоинт».

Ревью Astra, круг 3 (docs/reviews/2026-09-12-wms433/astra-review-round3.md,
дефект №26) показало, что оба предыдущих исправления решали конкретный
пример, а не принцип, и добавило ещё две проблемы:

9. **Пропуск**: многострочный блок без скобок/присваивания («    import
   os\n    import sys») не ловился — ``_INDENTED_CODE_LINE`` требовал скобку,
   двоеточие или ``=`` в каждой подозрительной строке. Заменил принцип: одна
   строка с отступом ловится, только если она либо начинается с
   Python-ключевого слова (``import``/``from``/``def``/``class``/``return``/
   ``if``/… ), либо это явное присваивание/вызов/строка со скобками —
   ``_CODE_LINE_PATTERN``; а весь блок считается кодом, если НАЙДЕНЫ ДВЕ
   ПОДРЯД такие строки (``_has_indented_code_block``) — единственная строка
   без пары (например голое «return x» без контекста) сама по себе не
   блокируется, зато реальный многострочный фрагмент (импорты, функции,
   присваивания) ловится независимо от того, есть ли скобки в каждой строке.
10. **Ложное срабатывание**: «В таблице FBS выберите заказ» резалось, потому
    что после «таблице» шло произвольное латинское слово (FBS). Настоящий
    признак внутреннего идентификатора — не «латиница после триггерного
    слова», а snake_case/CamelCase (есть `_` или переход строчная→заглавная)
    ИЛИ обратные кавычки вокруг слова независимо от его написания. «FBS»,
    «SKU», «ID» — обычные аббревиатуры интерфейса без подчёркивания и без
    смены регистра внутри слова, они больше не считаются идентификатором.
    ``_looks_like_technical_identifier`` проверяет это отдельно от поиска
    самого упоминания (``_TECH_NAME_TRIGGER``).

Ревью Astra, круг 4 (docs/reviews/2026-09-12-wms433/astra-review-round4.md,
дефект №33) прямо указало: три круга подряд чинили КОНКРЕТНЫЙ пример
ревьюера регулярками, а не принцип — и нашли пятый обход (плюс подтвердили,
что старые обходы №9/№10 закрыты не до конца). Здесь — смена принципа, а не
очередная подстройка:

11. **`sanitize_answer` делал `strip()` ДО проверки** — у входа «    import
    os\n    import sys» пропадал отступ ПЕРВОЙ строки (``strip()`` трогает
    только края ВСЕЙ строки, а не каждую строку по отдельности), и с ним —
    единственная опора старого правила «нужен отступ у каждой строки блока».
    Теперь `contains_unsafe_content` проверяет ИСХОДНЫЙ текст, `strip()` —
    только для оформления уже одобренного ответа. И само правило (см. п.13)
    больше не требует отступа как обязательного признака — это вторая,
    независимая причина, почему пропуск закрыт.
12. **Пустая строка и строка-комментарий сбрасывали счётчик соседних строк**
    («    total = 1\n\n    enabled = True», «def …():\n    # комментарий\n
    return True»). Старый принцип требовал ДВЕ ПОДРЯД строки. Новый принцип
    (п.13) считает кодовые строки по ВСЕМУ тексту, а не подряд идущими —
    пустая строка или комментарий между ними больше ничего не сбрасывают.
13. **Новый принцип для кода: признаки строки, а не отступ и не соседство.**
    ``_is_strict_code_line`` — строка (после обрезки пробелов у НЕЁ САМОЙ, а
    не всего текста) считается кодовой, если она: начинается с
    ``import``/``from``; начинается с ключевого слова Python-инструкции
    (``def``/``class``/``return``/``if``/``for``/``while``/``try``/
    ``except``/``with``); является присваиванием ``identifier = значение`` с
    ЛАТИНСКИМ именем слева (кириллица слева — это подпись вида «Статус =
    Черновик», не код); является вызовом ``identifier(...)``; заканчивается
    на ``{``/``}``/``;`` и при этом во всей строке нет кириллицы (иначе — не
    код, а обычная пунктуация); или начинается с SQL-ключевого слова.
    Комментарий (``# …``) сам по себе не считается кодом, но считается им,
    если РЯДОМ (соседняя строка до или после) есть настоящая кодовая строка
    — так «# комментарий» между «def …():» и «return True» больше не рвёт
    им счёт. Ответ небезопасен, если таких строк **две и более в любом месте
    текста**, либо ровно одна — но с отступом ≥4 пробелов (усиливающий
    признак, а не обязательное условие) или внутри ``` `` `` `` / ``~~~``.
14. **Точные внутренние имена вместо эвристики «похоже на идентификатор».**
    Старый принцип («snake_case/CamelCase или обратные кавычки») и пропускал
    реальные имена без этих признаков («Таблица users» — часто короткое имя
    без `_` и без смены регистра), и обходился любой другой кавычкой
    («Таблица "assistant_messages"», «функция 'submit_executor_result'» —
    регулярка ждала именно обратную кавычку или её отсутствие ПАРОЙ, а не
    любой символ), и ложно резал «В таблице `FBS`» просто из-за кавычек.
    Теперь список опасных слов — не эвристика, а ФАКТ: ``_INTERNAL_IDENTIFIERS``
    собирается из настоящего кода при импорте модуля — имена таблиц БД
    (``__tablename__`` во всех файлах ``app/models``) и имена функций/классов
    ``app/services`` и ``app/api``. Ответ небезопасен, если содержит любое из
    этих имён как ОТДЕЛЬНОЕ СЛОВО (``_mentions_internal_identifier`` разбивает
    текст на слова, а не ищет подстроку — «FBS» не «внутри» имени
    ``fbs_client_id``, это два разных слова) — независимо от регистра и от
    того, в каких кавычках оно упомянуто или без них вовсе. «FBS», «SKU»,
    «QR», «Excel», «WB», «nmID» не в этом списке (проверено: пересечений
    полного списка внутренних имён с этими и другими обязательными
    положительными фразами ревью не найдено — см. тесты и
    ``_IDENTIFIER_ALLOWLIST`` ниже), поэтому «В таблице FBS» / «в таблице
    `FBS`» проходят при любом оформлении кавычек.
15. Обратные кавычки сами по себе больше НЕ признак опасности (см. п.13/14 —
    опасность решают признаки строки и настоящий список имён, а не факт
    наличия кавычек); ``_has_suspicious_inline_code`` остаётся отдельной,
    более узкой проверкой на явный код ВНУТРИ инлайн-спана (скобки, `=`,
    `def`, `SELECT`) — то, что было её задачей и раньше.

Пути (`backend/...`, `.py`, `.tsx`), SQL-запрос целиком и невидимые символы —
без изменений с круга 1 (``_UNSAFE_PATTERNS``, ``_INVISIBLE_CHARS``).

После круга 4 (правка того же дефекта №33, найдено ведущим при финальной
проверке — не самим ревью Astra): старые секретные шаблоны ловили ключи
Anthropic (``sk-...``) и OpenAI по форме, а также JWT и AWS-ключи, но не
узнавали токены с собственным префиксом у других провайдеров — например,
``ghp_`` + 36 символов (личный токен GitHub) проходил насквозь, потому что
универсальный шаблон «длинная строка из [A-Za-z0-9+/]{40,}» не матчит строку,
разорванную подчёркиванием на «ghp» (3 символа) и «AAAA…A» (36 символов) — ни
один из кусков не набирает 40 подряд. Добавлены явные шаблоны по префиксу для
GitHub (``ghp_``/``gho_``/``ghu_``/``ghs_``/``github_pat_``), Slack
(``xoxa-``/``xoxb-``/``xoxp-``/``xoxr-``), Google (``AIza…`` — API key,
``ya29.…`` — OAuth-токen) и PEM-приватных ключей
(``-----BEGIN ... PRIVATE KEY-----``); шаблон ``sk-…`` расширен до
``[A-Za-z0-9_-]`` — реальные ключи Anthropic содержат дефисы
(``sk-ant-api03-...``), которые старый шаблон без дефиса в символьном классе
не покрывал целиком.

Ревью Astra, круг 5 (astra-review-round5.md, дефект №35) нашло, что правило
«≥2 строк кода или 1 строка с отступом ≥4» по-прежнему пропускало одиночную
строку без окружения и без отступа — `import os`, `print("hello")`,
`answer = 42`, код под маркером списка (`- import os`, строка не матчила
`^import`, потому что начиналась с «-») и код-фрагмент внутри предложения
(«Вот код: import os; print(os.getcwd())», вся строка целиком не была ни
импортом, ни вызовом). Добавлен независимый слой —
``_has_strong_single_line_code_signal``: маркер списка/цитаты снимается,
строка режется на сегменты по ``;``/``:``, и для СИЛЬНОГО признака (import/
from/def/class/return/SQL в начале сегмента, присваивание с латинским именем
без кириллицы в сегменте, вызов с кавычкой или точкой в цепочке перед
скобками) счёт и отступ больше не нужны — одного совпадения достаточно.

Тем же кругом ведущий (не само ревью) нашёл обратную проблему: в список из
3412 внутренних имён попали 15 коротких (≤6 символов) слов без "_" и без
смены регистра, которые оказались ОДНОВРЕМЕННО настоящим кодом и обычной
лексикой — «Login на портале селлера» и «Просмотр Health системы»
блокировались зря. ``_load_internal_identifiers`` теперь исключает такие
слова по форме (``_is_common_short_word``) ещё до ``.lower()``, плюс
``_IDENTIFIER_ALLOWLIST`` пополнен явным списком той же природы — подробности
в комментарии рядом с этими функциями.
"""

from __future__ import annotations

import re
from pathlib import Path

SAFE_REPLACEMENT_TEXT = (
    "Не могу показать это. Опишите, что вы хотите сделать, — подскажу шаги."
)

# Невидимые символы (zero-width space/joiner/non-joiner, word joiner, BOM),
# которыми можно попытаться разорвать сигнатуру ключа или пути на вид
# безобидных кусков. Убираем их до любой другой проверки.
_INVISIBLE_CHARS = re.compile(r"[​‌‍⁠﻿]")

# Ровно ПАРА обратных кавычек — инлайн-код целиком, без риска, что закрывающая
# кавычка одного span'а станет открывающей для следующего произвольного текста
# (см. п.5 в докстринге выше). Опасно, если внутри есть символ, который вообще
# не встречается в названии кнопки/пункта меню на человеческом языке.
_INLINE_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_INLINE_CODE_SUSPICIOUS = re.compile(r"[(){};=]|==|\bdef\b|\bSELECT\b", re.IGNORECASE)


def _has_suspicious_inline_code(text: str) -> bool:
    return any(_INLINE_CODE_SUSPICIOUS.search(span) for span in _INLINE_CODE_SPAN.findall(text))


# --- п.13: код по признакам строки, без опоры на отступ и соседство --------

_HAS_CYRILLIC = re.compile(r"[А-яЁё]")
_COMMENT_LINE = re.compile(r"^#\s")

# Каждый паттерн проверяется на уже обрезанной (``.strip()``) ОТДЕЛЬНОЙ
# строке — отступ строки к этому моменту уже неважен для самого решения
# «это код»: он используется дальше отдельно, только как усилитель для
# ОДИНОЧНОЙ найденной строки (см. ``_has_code_like_content``).
_CODE_LINE_RULES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:import|from)\s+\w"),
    re.compile(r"^(?:def|class|return|if|for|while|try|except|with)\b.*:?$"),
    # Присваивание — латинское имя слева (кириллица слева — это подпись,
    # «Статус = Черновик», не код).
    re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*\s*=\s*.+$"),
    # Вызов identifier(...) или identifier.method(...).
    re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*\(.*\)\s*;?$"),
    re.compile(r"^(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", re.IGNORECASE),
)


def _is_strict_code_line(stripped_line: str) -> bool:
    if not stripped_line:
        return False
    if any(p.match(stripped_line) for p in _CODE_LINE_RULES):
        return True
    # Заканчивается на {, } или ; — код, только если во всей строке нет ни
    # одной кириллической буквы (иначе это обычная пунктуация русского текста).
    return stripped_line[-1] in "{};" and not _HAS_CYRILLIC.search(stripped_line)


# --- круг 5, дефект №35: одиночная строка без отступа и код под маркером ---
#
# Правило выше («≥2 строк или 1 строка с отступом ≥4») пропускало одиночный
# `import os`, `print("hello")`, `answer = 42` без окружения (не набирается
# ни счёт 2, ни отступ), не распознавало код под маркером списка
# (`- import os` не матчит `^import`, потому что строка начинается с «-»),
# и не видело код-фрагмент внутри предложения («Вот код: import os;
# print(os.getcwd())» — вся строка целиком не является ни импортом, ни
# вызовом). Здесь — независимый, более узкий по составу, но не требующий
# ни счёта, ни отступа признак: несколько форм, которые нормальный связный
# русский текст не производит НИКОГДА (в отличие от «таблица»/«функция» —
# слов из круга 3, которые в обычной речи как раз встречаются).
_LIST_OR_QUOTE_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+|^\s*>\s*")


def _strip_line_markers(line: str) -> str:
    """Снять маркер списка (-, *, •, "1.", "1)") и цитаты (>) перед началом

    строки — возможна их комбинация («> - текст»), поэтому снимаем в цикле,
    пока строка меняется.
    """
    previous = None
    current = line
    while current != previous:
        previous = current
        current = _LIST_OR_QUOTE_MARKER.sub("", current, count=1)
    return current


# Сильный признак — конструкция, которую обычный человеческий текст (в том
# числе объясняющий что-то про экран или про число) не производит вообще,
# поэтому для неё не нужен ни счёт «≥2 строк», ни отступ.
_STRONG_LEADING_RULES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:import|from)\s+\w"),
    re.compile(r"^(?:def|class)\s+\w"),
    re.compile(r"^return\b"),
    re.compile(r"^(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", re.IGNORECASE),
)
# Присваивание: латинское имя слева и НИ ОДНОЙ кириллической буквы во всём
# сегменте — «Скидка = 10 %» (кириллица слева) и «delta = Черновик» (кириллица
# справа) этим не считаются кодом, только чужой лексикой пополам с числом/словом.
_STRONG_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*\s*=\s*\S")
# Вызов с кавычкой внутри скобок (print("hello")) или с точкой в цепочке
# перед скобками (os.getcwd()) — оба варианта нормальная фраза интерфейса не
# производит, поэтому здесь достаточно search(), а не привязки ко всей строке.
_STRONG_CALL_WITH_QUOTE = re.compile(r"\w+\([^)]*[\"'][^)]*\)")
_STRONG_CALL_WITH_DOT = re.compile(r"\w+\.\w+\([^)]*\)")


def _is_strong_code_segment(segment: str) -> bool:
    segment = segment.strip()
    if not segment:
        return False
    if any(p.match(segment) for p in _STRONG_LEADING_RULES):
        return True
    if _STRONG_ASSIGNMENT.match(segment) and not _HAS_CYRILLIC.search(segment):
        return True
    return bool(_STRONG_CALL_WITH_QUOTE.search(segment) or _STRONG_CALL_WITH_DOT.search(segment))


def _has_strong_single_line_code_signal(text: str) -> bool:
    """Не зависит от счёта строк и отступа — см. докстринг блока выше.

    Маркер списка/цитаты снимается перед проверкой; строка режется на
    сегменты по ``;``/``:``, чтобы ловить код, вставленный посреди фразы
    («Вот код: import os; print(os.getcwd())»), а не только строку целиком.
    """
    for raw_line in text.splitlines():
        line = _strip_line_markers(raw_line.strip())
        for segment in re.split(r"[;:]", line):
            if _is_strong_code_segment(segment):
                return True
    return False


def _has_code_like_content(text: str) -> bool:
    """Небезопасно, если кодовых строк ≥2 в любом месте текста (не обязательно

    подряд), либо ровно одна — но с отступом ≥4 пробелов, либо найден сильный
    признак одиночной строки/сегмента (см. ``_has_strong_single_line_code_signal``,
    круг 5, дефект №35). Комментарий (``# …``) сам по себе не код, но
    считается им, если рядом (соседняя строка) есть настоящая кодовая строка.
    """
    if _has_strong_single_line_code_signal(text):
        return True
    lines = text.splitlines()
    stripped_lines = [line.strip() for line in lines]
    strict = [_is_strict_code_line(s) for s in stripped_lines]
    counted = list(strict)
    for i, s in enumerate(stripped_lines):
        if strict[i]:
            continue
        if _COMMENT_LINE.match(s) and (
            (i > 0 and strict[i - 1]) or (i + 1 < len(strict) and strict[i + 1])
        ):
            counted[i] = True
    total = sum(counted)
    if total >= 2:
        return True
    if total == 1:
        idx = counted.index(True)
        if re.match(r"^[ \t]{4,}\S", lines[idx]):
            return True
    return False


# --- п.14: точные внутренние имена вместо эвристики -------------------------

_TABLENAME_PATTERN = re.compile(r'__tablename__\s*=\s*["\']([A-Za-z0-9_]+)["\']')
_DEF_PATTERN = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)", re.MULTILINE)
_CLASS_PATTERN = re.compile(r"^\s*class\s+([A-Za-z_]\w*)", re.MULTILINE)
_IDENTIFIER_TOKEN = re.compile(r"\w+")

# Круг 5 (находка ведущего, не самого ревью Astra): прогон обеих копий на
# реальном списке (3412 имён) нашёл 15 коротких слов без "_" и без смены
# регистра, которые оказались ОДНОВРЕМЕННО настоящими внутренними именами
# (login, health, status, users, products, now, one, has, me, wait, call,
# fetch, net, http, delta) И обычной лексикой ответа — «Login на портале
# селлера» и «Просмотр Health системы» блокировались, хотя ничего не
# раскрывали (нарушение R17: фильтр обязан резать секрет, а не ЛЮБОЙ ответ).
# Совпадение с реальным именем — необходимое, но НЕ достаточное условие для
# короткого слова без "_"/CamelCase: его от обычного слова языка отличить
# нельзя. Список — по факту найденного конфликта (как и раньше), с запасом
# на слова той же природы, которые не совпали СЕЙЧАС, но совпадут при
# следующем изменении кода (main, get, list, create, update, delete, user,
# order, item, product, seller, tenant, warehouse, supply, box, label,
# print, report, invoice, job, task, event, scan, code, chat, message).
# Имена с подчёркиванием (``assistant_messages``, ``submit_executor_result``)
# и CamelCase (``calculateStockLimit``) сюда не подпадают ни при какой длине.
_IDENTIFIER_ALLOWLIST: frozenset[str] = frozenset({
    "login", "health", "status", "users", "products", "now", "one", "has",
    "me", "wait", "call", "fetch", "net", "http", "delta", "main", "get",
    "list", "create", "update", "delete", "user", "order", "item",
    "product", "seller", "tenant", "warehouse", "supply", "box", "label",
    "print", "report", "invoice", "job", "task", "event", "scan", "code",
    "chat", "message",
    # Переоткрытый C13 (круг 8): те же слова, но найденные при сканировании
    # frontend/src — легитимные legacy-компоненты (frontend/src/ui/*.tsx,
    # упомянуты в AGENTS.md как «legacy Card/Input»), которые при этом ЕЩЁ и
    # обычные английские слова интерфейса ("нажмите кнопку", card/button как
    # заимствования). PascalCase не спасает их от фильтра, как коротких
    # чисто-числовых констант (_is_common_short_word требует ОТСУТСТВИЕ смены
    # регистра, а у "Button"/"Card" она есть) — поэтому здесь, по факту.
    "button", "card", "input", "select", "app", "tag", "screen", "section",
})


def _has_mixed_case(name: str) -> bool:
    """CamelCase/PascalCase — в имени есть и строчные, и заглавные буквы."""
    return name != name.lower() and name != name.upper()


def _is_common_short_word(raw_name: str) -> bool:
    """Круг 5: короткое (≤6 символов) имя без "_" и без смены регистра

    неотличимо от обычного слова языка — критерий по ФОРМЕ имени (а не
    заранее выдуманный список конкретных слов), чтобы ловить и будущие
    совпадения того же рода без ручного пополнения ``_IDENTIFIER_ALLOWLIST``
    при каждом новом коротком имени в коде. Проверяется на ИСХОДНОМ
    (до ``.lower()``) написании — после приведения к нижнему регистру
    признак «смена регистра» необратимо теряется.
    """
    return len(raw_name) <= 6 and "_" not in raw_name and not _has_mixed_case(raw_name)


def _load_internal_identifiers(app_dir: Path) -> frozenset[str]:
    """Настоящие внутренние имена: ``__tablename__`` из ``app/models`` и

    имена функций/классов из ``app/services``/``app/api``. Источник истины —
    файлы на диске, а не эвристика по написанию слова — КРОМЕ круга 5:
    короткие слова без "_"/CamelCase дополнительно исключаются по форме
    (``_is_common_short_word``) ещё ДО приведения к нижнему регистру.
    """
    raw_names: set[str] = set()
    models_dir = app_dir / "models"
    if models_dir.is_dir():
        for path in models_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            raw_names.update(m.group(1) for m in _TABLENAME_PATTERN.finditer(text))
    for sub in ("services", "api"):
        sub_dir = app_dir / sub
        if not sub_dir.is_dir():
            continue
        for path in sub_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            raw_names.update(m.group(1) for m in _DEF_PATTERN.finditer(text))
            raw_names.update(m.group(1) for m in _CLASS_PATTERN.finditer(text))
    names = {n.lower() for n in raw_names if not _is_common_short_word(n)}
    return frozenset(names) - _IDENTIFIER_ALLOWLIST


def _mentions_internal_identifier(text: str, identifiers: frozenset[str]) -> bool:
    if not identifiers:
        return False
    return any(token.lower() in identifiers for token in _IDENTIFIER_TOKEN.findall(text))


# --- переоткрытый C13 (круг 8): имена фронтенда — тот же жёсткий класс R17 --
#
# Ревью Opus по dba08e9b: список внутренних идентификаторов собирался только
# из backend/app — имена фронтовых компонентов/экранов работающей версии
# («FfInventoryListScreen», «AuthedAppLayout», «AssistantPanel») проходили к
# пользователю без замены в обеих копиях. По решению аналитика (R17, 4.3) это
# тот же жёсткий класс, что и имена таблиц/функций бэка — источник истины
# расширяется на ``frontend/src``.
#
# Форма имени: PascalCase (первая буква заглавная, есть хотя бы одна строчная
# — отличает "Component" от "CONST_NAME") ИЛИ хук ``useXxx`` (после "use" —
# заглавная буква). Только ЭТА форма — реальная проверка на живом дереве
# (345 файлов frontend/src) показала: без такого ограничения «голый» паттерн
# `function name(` ловит СОТНИ обычных служебных функций (`move`, `reset`,
# `submit`, `container`, `find`...) — слова, которые совершенно нормально
# появляются в объяснении интерфейса. С ограничением по форме список короче
# на порядок (333 вместо 1172 сырых имён на этом дереве) и состоит из
# компонентов/хуков — то, ради чего C13 и переоткрыли.
def _looks_like_frontend_component_or_hook(name: str) -> bool:
    if "_" in name:
        return False
    if name[:1].isupper() and any(c.islower() for c in name):
        return True
    return name.startswith("use") and len(name) > 3 and name[3].isupper()


# Определения (не импорты — паттерны ищут именно ОБЪЯВЛЕНИЕ, поэтому
# `import { Button } from '@mui/material'` никогда не совпадёт; «TableContainer»,
# упомянутый аналитиком, — библиотечное имя, в frontend/src не определено, и
# в списке его действительно нет, проверено прогоном). "export" необязателен
# у трёх последних паттернов — компонент может быть объявлен как есть и
# экспортирован позже отдельной строкой (`export { Name }`) или как
# default-export, ссылающийся на уже объявленное имя.
_FRONTEND_DEF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*export\s+(?:default\s+)?function\s+([A-Za-z_]\w*)", re.MULTILINE),
    re.compile(r"^\s*export\s+(?:default\s+)?class\s+([A-Za-z_]\w*)", re.MULTILINE),
    re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*[<(]", re.MULTILINE),
    re.compile(r"^\s*(?:export\s+(?:default\s+)?)?const\s+([A-Za-z_]\w*)\s*[:=]", re.MULTILINE),
)
_FRONTEND_FILE_EXTENSIONS = (".ts", ".tsx")


def _load_frontend_identifiers(frontend_src_dir: Path) -> frozenset[str]:
    """Настоящие имена компонентов/хуков/функций/классов из ``frontend/src``

    (и имена файлов компонентов — ``FfInventoryListScreen.tsx`` →
    "FfInventoryListScreen") — та же логика вычистки коротких обычных слов
    (``_is_common_short_word``/``_IDENTIFIER_ALLOWLIST``), что и для бэка.
    """
    raw_names: set[str] = set()
    if frontend_src_dir.is_dir():
        for path in frontend_src_dir.rglob("*"):
            if not path.is_file() or path.suffix not in _FRONTEND_FILE_EXTENSIONS:
                continue
            if path.suffix == ".tsx" and _looks_like_frontend_component_or_hook(path.stem):
                raw_names.add(path.stem)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in _FRONTEND_DEF_PATTERNS:
                for match in pattern.finditer(text):
                    name = match.group(1)
                    if _looks_like_frontend_component_or_hook(name):
                        raw_names.add(name)
    names = {n.lower() for n in raw_names if not _is_common_short_word(n)}
    return frozenset(names) - _IDENTIFIER_ALLOWLIST


# frontend/src НЕ входит в Docker-образ API — Dockerfile.railway копирует
# только app/tests/alembic (см. докстринг-комментарий ниже про снимок), в
# отличие от backend/app, который бэкенд сканирует живьём при импорте (тот
# же процесс, что и работающий код). Поэтому для фронтенда — не живой скан,
# а закоммиченный снимок; см. ``_load_frontend_identifiers_snapshot`` ниже.
_FRONTEND_IDENTIFIERS_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent / "assistant_frontend_identifiers.txt"
)


def _load_frontend_identifiers_snapshot(
    path: Path = _FRONTEND_IDENTIFIERS_SNAPSHOT_PATH,
) -> frozenset[str]:
    """Прочитать снимок имён фронтенда — по одному имени на строку.

    Снимок генерируется командой ``python -m app.services.assistant_safety
    --refresh`` (сканирует настоящий ``frontend/src`` той же ``_load_frontend_identifiers``,
    что использует и исполнитель на своём checkout'е) и коммитится в git;
    ``backend/tests/test_assistant_safety.py`` проверяет, что он не отстал от
    реального ``frontend/src`` — CI не даст ему устареть молча.
    """
    if not path.is_file():
        return frozenset()
    lines = path.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip())


# Считается один раз при импорте модуля: бэкенд — тот же процесс, что и
# ``app/models``/``app/services``/``app/api``, поэтому список всегда
# актуален для реально работающего кода без отдельного обновления. Имена
# фронтенда — из закоммиченного снимка (см. выше), не живым сканом.
_APP_DIR = Path(__file__).resolve().parent.parent
_INTERNAL_IDENTIFIERS: frozenset[str] = (
    _load_internal_identifiers(_APP_DIR) | _load_frontend_identifiers_snapshot()
)


def _refresh_frontend_identifiers_snapshot() -> int:
    """Пересканировать настоящий ``frontend/src`` и перезаписать снимок.

    Возвращает число найденных имён — используется CLI ниже
    (``python -m app.services.assistant_safety --refresh``) и напрямую тестом
    на устаревание снимка.
    """
    repo_root = _APP_DIR.parent.parent
    frontend_src = repo_root / "frontend" / "src"
    names = _load_frontend_identifiers(frontend_src)
    _FRONTEND_IDENTIFIERS_SNAPSHOT_PATH.write_text(
        "\n".join(sorted(names)) + ("\n" if names else ""), encoding="utf-8"
    )
    return len(names)


# Умышленно избыточные, а не точные шаблоны: ложное срабатывание всего лишь
# заменит ответ на безопасную фразу (пользователь может переспросить иначе),
# а пропуск утечки — необратим. При сомнении фильтр должен сработать.
_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Блок кода в ``` / ~~~ — коду не нужна пара кавычек.
    re.compile(r"```"),
    re.compile(r"~~~"),
    # SQL — re.DOTALL, чтобы перенос строки между ключевыми словами не спасал
    # запрос от обнаружения.
    re.compile(
        r"\b(SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|"
        r"CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    # Пути файлов проекта / файловой системы.
    re.compile(r"\b(backend|frontend|app|tools)[/\\][\w./\\-]*\.(py|ts|tsx|js|jsx|sql|json|ya?ml|env)\b"),
    re.compile(r"\b[\w./-]+\.(py|tsx?|jsx?|sql)\b"),
    re.compile(r"(^|\s)/[\w.-]+/[\w./-]+"),
    re.compile(r"[A-Za-z]:\\\\[\w\\.-]+"),
    # Похоже на секрет: JWT, длинные base64/hex-строки, явные ключи API.
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    # Токены с собственным префиксом у конкретных провайдеров — находка
    # ведущего после круга 4: универсальный шаблон «длинная строка» ниже не
    # ловит их, потому что подчёркивание/дефис в самом префиксе разрывает
    # подряд идущие символы на куски короче порога (см. докстринг модуля).
    re.compile(r"\bgh[opus]_[A-Za-z0-9]{16,}\b"),  # ghp_/gho_/ghu_/ghs_ — GitHub
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b"),  # Slack
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),  # Google API key
    re.compile(r"\bya29\.[A-Za-z0-9_-]{10,}\b"),  # Google OAuth access token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    re.compile(
        r"(пароль|секрет|ключ|токен|password|secret|token|api[_-]?key)\s*[:=]\s*\S{5,}",
        re.IGNORECASE,
    ),
    # Просьба показать саму инструкцию — если она случайно процитирована в
    # ответе (эхо провокации), а не отклонена.
    re.compile(r"(системный промпт|system prompt|инструкция модели)", re.IGNORECASE),
)


def contains_unsafe_content(text: str) -> bool:
    """True, если текст похож на код/путь/SQL/секрет/внутреннюю инструкцию."""
    cleaned = _INVISIBLE_CHARS.sub("", text)
    if _has_suspicious_inline_code(cleaned):
        return True
    if _has_code_like_content(cleaned):
        return True
    if _mentions_internal_identifier(cleaned, _INTERNAL_IDENTIFIERS):
        return True
    return any(pattern.search(cleaned) for pattern in _UNSAFE_PATTERNS)


def sanitize_answer(text: str) -> str:
    """Вернуть текст как есть, если он безопасен, иначе — безопасную замену.

    Ревью Astra круг 4 (дефект №33, п.11 докстринга модуля): проверка — на
    ИСХОДНОМ тексте, ``strip()`` — только для оформления уже одобренного
    ответа. Раньше было наоборот, и ``strip()`` (обрезающий края всей строки
    целиком, а не каждую строку) снимал отступ первой строки многострочного
    кода до того, как до неё доходила проверка.
    """
    if contains_unsafe_content(text):
        return SAFE_REPLACEMENT_TEXT
    stripped = text.strip()
    if not stripped:
        return SAFE_REPLACEMENT_TEXT
    return stripped


if __name__ == "__main__":
    # Переоткрытый C13 (круг 8): "python -m app.services.assistant_safety
    # --refresh" — перегенерировать снимок имён frontend/src (см.
    # ``_refresh_frontend_identifiers_snapshot`` выше). Запускать из каталога
    # ``backend`` после любых изменений в frontend/src, добавляющих/переименовывающих
    # экспортируемые компоненты/хуки, и коммитить обновлённый файл — тест
    # ``TestFrontendIdentifierSnapshotIsFresh`` проверяет, что снимок не устарел.
    import sys as _sys

    if "--refresh" in _sys.argv[1:]:
        _count = _refresh_frontend_identifiers_snapshot()
        print(f"Снимок обновлён: {_FRONTEND_IDENTIFIERS_SNAPSHOT_PATH} ({_count} имён)")
    else:
        print("Использование: python -m app.services.assistant_safety --refresh", file=_sys.stderr)
        _sys.exit(2)
