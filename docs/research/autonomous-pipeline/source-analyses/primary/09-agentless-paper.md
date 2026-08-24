# Agentless paper — staged repair без свободной trajectory

**Источник:** [Xia et al., 2024, arXiv:2407.01489](https://arxiv.org/abs/2407.01489), проверено 2026-08-24. **Класс:** E3 paper, подкреплён E1 [pinned code](https://github.com/OpenAutoCoder/Agentless/tree/5ce5888b9f149beaace393957a55ea8ee46c9f71).

## Подтверждённый flow

Paper разделяет SWE задачу на hierarchical localization, repair и patch validation. Localization последовательно сужает репозиторий до files, затем classes/functions, затем lines; repair получает этот срез, генерирует конечное множество candidates; validation выполняет tests и выбирает patch. В отличие от shell-agent, состояние — явные stage outputs, а budget — конечное число моделей/candidates.

## Что не следует достраивать

Авторы не доказывают, что эта схема умеет собирать продуктовые требования, предотвращать визуальный редизайн, сохранять controller state после инфраструктурной смерти, выполнять browser QA или безопасно merge-ить в shared main. Test pass — benchmark metric, не human acceptance.

## WMS-вердикт — взять в качестве анти-петли

Использовать идею изолированных, проверяемых промежуточных артефактов и finite branching: сначала scope/impact assertion, потом bounded coherent repair. Не превращать анализатор кода в Product/UX authority.

## Evidence

- [paper PDF](https://arxiv.org/pdf/2407.01489)
- [source commands/artifacts](https://github.com/OpenAutoCoder/Agentless/blob/5ce5888b9f149beaace393957a55ea8ee46c9f71/README.md)
- [SWE-bench evaluator](https://github.com/SWE-bench/SWE-bench)
