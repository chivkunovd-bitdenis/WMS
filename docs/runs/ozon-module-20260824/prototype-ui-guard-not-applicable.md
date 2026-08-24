# Prototype UI guard availability

На базовом SHA `d0cfab0abc3054183081925a860c27b15f2f4ebc` отсутствует файл `scripts/ui/ui_guard.py` и альтернативный UI guard под `scripts/`. Поэтому check `prototype-ui-guard` завершился exit 2 до анализа frontend-кода и не является находкой прототипа.

Машинная TypeScript/Vite-сборка выполняется отдельным check `prototype-build-repaired`. Геометрия, переполнения, кликабельность, состояния и соответствие существующему UI проверяются отдельным live-browser clicker на сохранённом commit SHA.
