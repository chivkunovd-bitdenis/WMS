# Claude Code #4462 — подагент заявляет запись, которой нет

## 1–2. Ссылка, класс, доказательность

Источник: [GitHub issue #4462](https://github.com/anthropics/claude-code/issues/4462), проверен 2026-08-24; автор указывает Claude Code 1.0.61, macOS 15.5, Node 24.4.1 и Next.js/TypeScript. E3: автор приводит точный Task prompt, наблюдаемую таблицу control test и shell-проверки. В прочитанном issue не видно подтверждения maintainer; это не доказательство дефекта всех версий.

## 3–5. Задача, система, happy path

Проверяется минимальная задача: custom subagent создаёт `agent-file-test.md`. Компоненты: main Claude, Task subagent, Write tool, sandbox/filesystem и внешние `ls`/`find`. Happy path: Task → Write returns success → файл существует на shared filesystem → виден в listing и Git. Это не full coding pipeline, Git/CI/browser отсутствуют.

## 6–13. Переходы, решения и контроли

Найденный переход «tool сказал success → следующий этап» ошибочен. Автор проверял existence внешними командами и получил: subagent сообщает creation, но файла нет; direct Write main session работает. В описании указана нестабильность первой попытки и последующие отказы. Prompt/scheme — ровно простой текстовый task; persisted artifact должен быть файл. Retry/resume нет. Scope минимален, budget не указан; loop control нет. Решения о том, верить ли report, не могут принадлежать модели: `test -f`, line count, Git status/content check должны исполняться контроллером.

## 14. Слабости

Данные — один пользователь и одна связка версий. Автор считает directory listings агента «mock», но это наблюдение, не установленный механизм sandbox. Даже при настоящем runtime bug этот кейс не доказывает, что любой subagent write ненадёжен.

## 15–16. WMS-применимость и вердикт

Адаптировать целиком как hard artifact gate: после каждой подзадачи controller проверяет, что ожидаемые файлы существуют в конкретном worktree, имеют ожидаемое содержимое и попали в `git diff`; до этого нельзя route дальше. В WMS это особенно относится к CONTRACT, evidence screenshots и browser verdict. Отвергнуть идею «подагент вернул подробный текст, значит файл создан».

## 17. Evidence links

- [Описание и матрица Task vs direct Write](https://github.com/anthropics/claude-code/issues/4462) — “Bug Description” и “Systematic Test Results”.
- [Команды внешней проверки](https://github.com/anthropics/claude-code/issues/4462) — reproduction steps `ls`/`find`.
