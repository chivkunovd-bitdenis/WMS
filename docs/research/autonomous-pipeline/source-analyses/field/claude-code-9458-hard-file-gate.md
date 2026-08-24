# Claude Code #9458 — частичный sandbox и hard file gate

## 1–2. Ссылка, класс, доказательность

Источник: [GitHub issue #9458](https://github.com/anthropics/claude-code/issues/9458), проверен 2026-08-24. Автор сообщает воспроизведение на v2.0.14, macOS/iTerm2 и связывает с #4462. E3: подробный диагностический набор и конкретный workaround, но maintainer-confirmation в прочитанном тексте отсутствует.

## 3–5. Система и путь

Автор запускает custom subagents, ожидая markdown-артефакты под `docs/32-agents/...`; наблюдает пустые directories без `index.md`. Happy path у предложенного workaround: isolated subagent возвращает текст, main session пишет его в filesystem и немедленно валидирует. Это workaround topology, не встроенная гарантия Claude Code.

## 6–13. Механика

Установленный автором gate состоит из четырёх проверок: file existence, line count, Git tracking, content validation. При первом failure процесс должен остановиться, а не продолжить fan-out «41 плохих агентов». Здесь модель производит текст/предложение, а main/controller выполняет запись и детерминированные проверки. Реальных prompts сверх примера нет; browser/CI/retry/Git publish не входят в источник. Контроль loops — stop-at-first-failure, не retry до успеха. Утверждение «95% quality + 100% reliability» — авторская оценка, не экспериментальный результат.

## 14. Слабости

Диагноз «partial sandboxing» — гипотеза автора. Workaround меняет архитектуру и может потерять контекст/форматирование, поэтому не следует использовать как универсальный транспорт кода без проверки patch.

## 15–16. WMS-применимость и вердикт

Взять минимальный принцип: карточка обязана иметь expected artifact manifest, а control-plane проверяет existence/content/Git location до следующей роли. Адаптировать текст-return fallback только для research/docs: для кода безопаснее проверять patch в designated worktree, не переписывать его главным агентом. Не брать заявленную оценку качества и не делать file-gate заменой тестам.

## 17. Evidence links

- [Описание empty directory и воспроизведение](https://github.com/anthropics/claude-code/issues/9458).
- [Четырёхшаговый validation protocol и workaround](https://github.com/anthropics/claude-code/issues/9458) — “Production-Tested Workaround”.
