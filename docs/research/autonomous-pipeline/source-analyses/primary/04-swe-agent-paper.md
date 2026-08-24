# SWE-agent paper — интерфейс агента как контролируемая граница

**Источник:** [Yang et al., 2024, arXiv:2405.15793](https://arxiv.org/abs/2405.15793), проверено 2026-08-24. **Класс:** E3 paper + E1 linked implementation. **Что доказано:** авторы измеряют влияние Agent-Computer Interface (ACI) на SWE-bench; paper не описывает production overnight SDLC.

## Механика по sections

В sections 2–3 ACI заменяет сырой terminal interaction командами/форматами, удобными модели: repository navigation, file viewing/editing и execution feedback. Figure/метод описывают trajectory: issue → repeated action/observation → patch → SWE-bench test evaluation. Основной вывод — интерфейс инструмента сильно влияет на результат, поэтому prompt роли без управляемого action surface слабее исполнимого контракта.

## Переходы и контроль

Модель выбирает действие; ACI детерминированно выполняет/форматирует observation. Termination по лимиту шагов либо submit. Acceptance — внешний SWE-bench harness. Paper не подтверждает human escalation, retry taxonomy, checkpoint/resume, PR/CI, browser testing, file scope или production cost control кроме экспериментальных лимитов.

## WMS-вердикт — взять принцип, не организацию

Для Developer: дать маленький typed набор действий и короткие diagnostics вместо безграничного shell transcript. Не переносить benchmark submit как критерий готовности: в WMS оно должно запускать независимые гейты.

## Evidence

- [paper PDF](https://arxiv.org/pdf/2405.15793)
- [implementation, pinned](https://github.com/SWE-agent/SWE-agent/tree/3ea751c087f32b16e039a2233dd6eefecef325d5)
- [SWE-bench harness](https://github.com/SWE-bench/SWE-bench)
