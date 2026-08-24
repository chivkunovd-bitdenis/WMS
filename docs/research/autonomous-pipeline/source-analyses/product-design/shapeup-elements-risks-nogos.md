# Shape Up — Find the Elements; Risks and No-Gos

## 1–2. Источник и доказательность

[Find the Elements](https://basecamp.com/shapeup/1.3-chapter-04) и [Risks and No-Gos](https://basecamp.com/shapeup/1.3-chapter-05), Shape Up/Basecamp, проверены 2026-08-24 (вторая страница вернула ошибку браузерного чтения, URL сохранён как первичный permalink). E2 для доступной главы; содержание второй главы требует повторной live-проверки перед цитированием деталей.

## 3–5. Задача и путь

Find the Elements разбивает shaped idea на ключевые affordances и places, нужные для завершения core path, вместо полного specification. Risks and No-Gos фиксирует известные сложные зоны, невозможные/нежелательные направления и вопросы, которые нельзя оставлять исполнителю как бесконечный поиск. Путь: core solution → элементы → связи/flow → риски → явные no-gos → handoff.

## 6–13. Исполнимые pre-design gates

Для **нового модуля** перед макетом нужен `ELEMENTS-RISKS` list: essential elements с user task; sequence/relationship; data dependency; one test scenario; risk/unknown; decision owner; no-go/de-scope condition. Для **локальной правки** достаточно: элемент/зона, intended delta, explicit «не менять» и regression risk. Модель способна сопоставить элементы с current screen и предложить low-fi delta; код валидирует scope/manifest; человек должен решать только риск, который меняет бизнес-политику. Артефакты — element map + risk/no-go list. Prompts/Git/retry/browser acceptance в главах не описаны.

## 14. Границы

Elements — не список всех UI widgets и не разрешение придумать новые requirements. No-go помогает ограничивать scope, но не заменяет test evidence. Полный текст второй страницы в этой сессии не был доступен через browser, поэтому не приписываются ей точные механизмы beyond её явно заданного предмета.

## 15–16. WMS-применимость и вердикт

Адаптировать для новых reporting modules: сначала назвать нужные элементы (например, период, общий объём, тара/ячейка, стоимость, export) и связь каждого с operator decision; затем обозначить no-go (не становиться inventory-editing screen, не redesign навигации). Для локального fix — только delta/no-go manifest. Вердикт: взять как structured pre-design artifact; не превращать в новый набор постоянных ролей.

## 17. Evidence

- [Find the Elements](https://basecamp.com/shapeup/1.3-chapter-04).
- [Risks and No-Gos permalink](https://basecamp.com/shapeup/1.3-chapter-05) — URL зафиксирован; контент в текущей проверке недоступен.
