1. Классы и ссылки на тесты в навыке аналитика — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
2. Новый навык тестировщика, включая красный новый тест и временную порчу для сохраняемого поведения — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
3. Запрет разработчику менять контракт и охрану, остановка при конфликте Cn/Rm — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
4. Проверка «Класс/Тест» и неизменности файлов после коммита контракта — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
5. Добавление зарегистрированного guard-теста разрешено, изменение/удаление базового защищённого файла запрещено — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
6. `promote_guards.py` с `git mv`, правкой импортов, документа и MANIFEST плюс временный Git-репозиторий в тесте — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
7. Одинаковый процесс в AGENTS.md и CLAUDE.md — сделано — `007faa12a06f68300ce8a700d7ca41fd7b2dbc4d`.
8. Публикация ветки — не сделано — `git push` прямо запрещён заданием.
Что проверено командой: `python -m unittest discover -s scripts/ci -p 'test_check_task_documents.py'`; `python -m unittest discover -s scripts/ci/tests -p 'test_*.py'`; `python scripts/ci/check_task_documents.py origin/etalon`; `ruff check` изменённых Python-файлов; `git diff --check`.
