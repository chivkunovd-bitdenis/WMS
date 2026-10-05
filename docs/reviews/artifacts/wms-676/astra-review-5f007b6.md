# WMS-676 — независимое Astra high ревью

**Вердикт: FAIL. Установка этого кандидата не получает PASS.**

Проверен продуктовый SHA **`5f007b6e22bce6a36f2255e239e7d3891c2af0bd`**
от 06.10.2026, опубликованный в `origin/codex/wms676-sol61-pipeline`.
Локальный HEAD и `git ls-remote origin refs/heads/codex/wms676-sol61-pipeline`
совпали с этим SHA перед проверками. Коммит настоящего отчёта не заменяет
проверенный продуктовый SHA.

Ревью выполнено по прямому поручению владельца без навыков и новых агентов.
До анализа прочитаны целиком AGENTS.md, CLAUDE.md, требования WMS-676,
owner-cases.md и failure-cases.md. AGENTS.md и CLAUDE.md побайтово одинаковы;
origin/etalon обновлён для сравнения правил. Предмет проверки — опубликованный
кандидат, а не новая реализация от etalon. Из библиотек применены проверки
неопределённого внешнего результата, повторов, соседнего состояния и различения
проверенного кода, тестов и фактической установки.

Разрешённый изменяемый файл — только этот отчёт. Код продукта, контрактные тесты,
конфигурация и установленная Telegram-служба не изменялись. Исходный чужой
`wms676-runtime-repair-result.txt` не читался и не изменялся. Все дополнительные
эксперименты использовали временные искусственные каталоги, базы и процессы.
Реальный `launchctl bootout/bootstrap` не вызывался; опасные команды в экспериментах
перехватывались до выполнения. Ключи, авторизация и production DB не затрагивались.

## Блокирующие замечания

### F1 · P1 · Замена PID до установки заглушки оставляет работающий worker вне ожидания

Место: `docs/reviews/artifacts/wms-676/install_sol61.py:152–170, 102–126`.

`main()` запоминает PID, проверяет отсутствие дочерних процессов и затем делает
снимок состояния и резервные копии. Заглушка устанавливается только после этого.
Если прежний worker завершился или упал в этом интервале, KeepAlive мог уже
запустить замену, которая прочитала настоящий `__main__.py`. Атомарная замена файла
не превращает уже загруженный код этого процесса в заглушку.

В `drain_and_bootout()` несовпадение `service_pid()` с исходным PID лишь пропускает
SIGTERM. В `tracked` остаётся только прежний PID. Когда его уже нет в `ps`, цикл
сразу заканчивается и вызывает `bootout`, хотя новый настоящий worker и его работа
не завершены. Комментарий «the next process is gated» здесь неверен: процесс мог
стартовать **до** границы замены файла.

**Воспроизведено:** настоящий Python-worker завершён и reaped; его замена запущена
из прежнего `__main__.py` до вызова `drain_and_bootout(old_pid)`. Функция дошла до
`bootout` при живой замене. Команда перехвачена и вместо неё выброшено исключение;
реальная служба и launchd не использовались. Вывод:

```text
REAL_PROCESS_REPRO: bootout reached while replacement worker alive; old PID was reaped before gate
```

Нужно исключить предположение, что любой новый PID обязательно выполняет заглушку.
При смене владельца процесса требуется безопасно установить его фактический режим
и дождаться всей прежней работы либо прекратить установку без bootout. Повторная
проверка idle сама по себе не создаёт атомарной границы.

### F2 · P1 · Дочерний процесс может отделиться до первого снимка и не попасть в tracked

Место: `install_sol61.py:103–126`.

Трекер начинает с одного родительского PID и узнаёт потомков только по текущему
PPID в периодических снимках `ps`. После SIGTERM старый worker ещё может создать
модель. Если родитель завершится или упадёт до первого наблюдения этого ребёнка,
у ребёнка уже будет PPID=1. Его связь с `tracked` потеряна, хотя он продолжает
работать. Аналогичное окно существует между опросами для промежуточного потомка.

Существующий `test_orphaned_descendant_also_finishes_before_bootout` сначала
показывает ребёнка с прежним PPID и только на следующем опросе делает его сиротой.
Поэтому он подтверждает ожидание **ранее замеченного** потомка, но не этот случай.
Обычные ThreadPoolExecutor-потоки действительно задерживают нормальный выход
родителя до завершения вызова; это не покрывает crash родителя или отделение
вложенного процесса.

**Воспроизведено:** настоящий Python-worker после SIGTERM создал настоящий дочерний
процесс и завершился через `os._exit(0)`. Первый снимок сделан после выхода родителя,
пока ребёнок ещё работал. В реальном `ps` ребёнок имел PPID=1. Установщик всё равно
дошёл до `bootout`. Команда перехвачена; ребёнок завершился естественно:

```text
REAL_ORPHAN_REPRO: bootout requested while never-observed final-tick child is alive with PPID=1
SYNTHETIC_CHILD_NATURALLY_FINISHED; real launchctl and TG never called
```

Это прямое нарушение границы R8 «естественное завершение прежнего процесса и его
дочерних процессов до bootout». Эксперимент доказывает преждевременное разрешение
bootout, а не реальное убийство процесса launchd: последнее намеренно не исполнялось.
Нужен способ учитывать работу независимо от исчезающей связи PID/PPID; одно
уменьшение интервала опроса гонку не закрывает. Неопределённый остаток работы не
должен разрешать bootout и изменение установленного пакета.

### F3 · P1 · После проверки SHA установщик повторно читает изменяемый checkout

Место: `install_sol61.py:146–151, 196–205, 220–226`.

Соответствие checkout опубликованному коммиту проверяется до drain, который может
занять до часа. Сами устанавливаемые байты потом читаются из `ROOT / path` заново.
Итоговые хеши и сравнение всех модулей также сравнивают установку с текущим checkout,
а не с Git-объектами проверенного SHA. Работа другого исполнителя во время ожидания
может поэтому попасть в службу без публикации и ревью, а отчёт всё равно заявит
`all_package_modules_match_commit: true` для исходного SHA.

**Воспроизведено:** штатная изолированная fixture установщика, настоящий файл и
искусственная SQLite. После успешного drain подменены только байты исходного
`worker.py` во временном checkout; исходный `git show sha:path` в fixture продолжал
возвращать опубликованные байты. `main()` успешно установил новые неопубликованные
байты и сформировал положительный отчёт:

```text
REPRO_SOURCE_RACE: unpublished bytes installed; all_package_modules_match_commit=True; installed_sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

Это исполнение реального кода установщика с поддельными внешними командами,
не реальная TG-установка. Для исправления источник установки должен быть неизменным:
байты точного Git-коммита либо заранее подготовленный проверенный набор файлов.
Заключительную проверку также надо делать относительно SHA. Нынешний тест dirty
checkout проверяет только изменение **до** предварительной проверки.

## Отдельный вердикт по требованиям

PASS ниже означает результат ревью кода и локальных проверок в названной области.
Он не означает установку, приёмку всего процесса или зелёный полный CI.

| Требование | Вердикт | Основание и границы |
|---|---|---|
| R1 | PASS для маршрутизации | `model_for`, `available_clis`, `agent_turn` и coordinator принудительно выбирают Sol 6.1/Codex для рабочих ролей и Astra high для review. Старые preference/job/config не меняют выбор; проверены native и обычные пути. Фактический запуск CLI в этом ревью не выполнялся. |
| R2 | PASS | Ошибка/лимит рабочей модели и ошибка/пауза Astra не переходят на другой provider/model. Night сохраняет текущий шаг и назначает повтор. Проверены model_migration, llm_router, pipeline_chat и night. |
| R3 | PASS для миграции истории | Миграция background_context транзакционна и выполняется один раз, прежние значения сохраняются; literal substr-границы не смешивают wildcard/nested task keys. Проверены handoff, разные роли/режимы, повторное создание router и native job. Установочная граница остаётся FAIL R8. |
| R4 | PASS для продуктовой миграции | Новая модель не пересоздаёт ticket/job, не сбрасывает этап, контракт, замечания, номер, версии и существующий код. В fixture установщика сохранён результат последнего оборота. Защита самой установки от гонок недостаточна — см. R8. |
| R5 | PASS | Исправление crosscheck `2c83492f42b2b2bd65d6a18e81dca5a726d239ee` присутствует: больше нет исключения единственного Codex provider, передаются `cli_only="codex"`, `session_key="review"`. Router выбирает Astra high; тесты подтверждают отдельный review-контекст и ошибку без fallback. Night/hotfix сохраняют отдельные ключи разработчика и ревьюера. |
| R6 | PASS | AGENTS.md=CLAUDE.md, README, пример конфига, активные prompts/instructions согласованы с Sol для работы и Astra high для ревью. Новый пользовательский режим миграции не введён. Старые неактивные Claude defaults не создают действующий маршрут через router. |
| R7 | PASS | Реестр коррекции принимает только `gpt-6-astra`, `high`, `PASS`; проверки Sol high/low отвергаются. 41 unit-тест CI-документов и два subtest прошли; ограничения реестра сохранены. |
| R8 | **FAIL** | F1 и F2 разрешают bootout до завершения работы; F3 позволяет установить байты вне проверенного SHA. Положительные обычные/таймаутные/rollback-тесты этих гонок не устраняют. Новая установка не выполнялась и не разрешается этим отчётом. |

## Что подтвердилось на безопасных путях

Атомарная заглушка действительно не импортирует runner или handler. У пустого
`support_agent/__init__.py` нет побочного запуска. Размер временного `__main__.py`
отличается от исходного, что препятствует совпадению timestamp/size bytecode cache.
В отдельном опыте запускалось именно `python -m support_agent`, а не только файл
заглушки: настоящий старый worker получил SIGTERM, выполнил последний дочерний
процесс, завершился, затем новая копия осталась в заглушке без второго запуска
worker. Команда bootout была разрешена тестовой обвязкой лишь после этого:

```text
REAL_PROCESS_PASS: final-tick model completed; old worker exited; -m support_agent gate started no second worker
```

При штатном таймауте код не делает SIGKILL/bootout и восстанавливает entrypoint.
При ошибке check-config после известной остановки возвращает сохранённые файлы и
конфиг. После попытки bootstrap не делает принудительный rollback: неизвестный
результат новой работы не закрывается её убийством. Эти ветви прошли тесты.

SQLite резервируется после завершения старого процесса; сохранён результат его
последнего оборота. Логический хеш всей базы проверяется до bootstrap. Успешная
изолированная установка меняет только пять заявленных настроек выбора модели/CLI;
остальные значения искусственного конфига, включая контрольное поле под секрет,
сохранились. Это проверка кода и поддельной конфигурации, не чтение реальных ключей.
Baseline проверяется по всем перечисленным пакетным файлам; WMS-664/WMS-668 не
откатываются намеренной заменой пакета на старую базу.

Дополнительная граница восстановления: `finally` не выполняется при SIGKILL
самого установщика или выключении машины. Тогда временная заглушка может остаться,
а обычный повтор откажет из-за отличия baseline. Резервная копия entrypoint
сохраняется заранее, но автоматического восстановления такого прерванного запуска
нет. Восстановление должно происходить отдельно после выяснения состояния процессов;
нельзя считать прежний backup доказательством отсутствия продолжающейся работы.
Это отмеченная эксплуатационная граница, не отдельный воспроизведённый FAIL.

Эксклюзивной блокировки двух установщиков в коде нет. Воспроизведённая конкуренция
в F3 — изменение checkout другим исполнителем. Два параллельных `main()` отдельно
не запускались; безопасность такой операции этим ревью не подтверждена.

## Выполненные проверки

Из `tools/support_agent`:

```sh
python3 -m pytest -q -p no:cacheprovider tests/test_model_migration.py tests/test_llm_router.py tests/test_pipeline_chat.py tests/test_agent_runtime.py tests/test_agent_coordinator.py tests/test_night.py tests/test_owner_and_hotfix.py tests/test_runner_and_safety.py tests/test_install_model_migration.py
```

Результат: **253 passed in 19.43s**, включая 11 тестов установщика. Это заново
выполненный прогон данного SHA, а не перенос прежнего результата 243 PASS.
Свободное место перед прогоном — около 1.0 GiB; disk I/O/No space ошибок не было.
Дополнительные синтетические воспроизведения F1–F3 находятся ниже и не входят
в 253 существующих теста.

Из корня:

```sh
python3 -m pytest -q -p no:cacheprovider scripts/ci/test_check_task_documents.py
python3 scripts/ci/check_task_documents.py b18026e8f580f419a6d72a356c513f7e66336648
python3 -m ruff check docs/reviews/artifacts/wms-676/install_sol61.py tools/support_agent/support_agent tools/support_agent/tests/test_install_model_migration.py tools/support_agent/tests/test_model_migration.py tools/support_agent/tests/test_pipeline_chat.py
python3 -m mypy --follow-imports=skip docs/reviews/artifacts/wms-676/install_sol61.py
git diff --check
```

CI unit: **41 passed, 2 subtests passed in 30.30s**. Проверка документов, Ruff и
`git diff --check` прошли. Mypy: **Success: no issues found in 1 source file**.
Контракт установщика не менялся между `e009c3fc0` и проверенным SHA.
Прежний RED на старом коде в этом ревью повторно не запускался; его история
сохранена в требованиях и не выдаётся за новое измерение.

Bundled absolute path присутствует в установщике и проверяется на существование
и executable bit. `SOL61_OK` от настоящего bundled CLI — факт, переданный владельцем
о проверке root; он **не воспроизводился этим ревьюером**. Вызовы fake `_run_once`,
fake AppServerTurn и цитаты исходного кода не считаются запуском Sol/Astra CLI.

## Воспроизводимые дополнительные проверки

Следующие программы запускались через `python3 -` из корня. Они импортируют
проверенный установщик, но переназначают APP/ROOT/внешние команды до вызова его
операций. Они не вызывают `main()` с реальными параметрами установленной службы.

### F1 и положительный опыт: настоящие процессы, перехваченный launchctl

```python
import importlib.util, subprocess, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace

installer = Path('docs/reviews/artifacts/wms-676/install_sol61.py').resolve()
WORKER = '''import pathlib, signal, subprocess, sys, time
p=pathlib.Path.cwd(); stop=False
def term(*_):
    global stop
    stop=True
signal.signal(signal.SIGTERM,term)
with (p/'starts').open('a') as f: f.write('worker\\n')
while not stop: time.sleep(.01)
subprocess.run([sys.executable,'-c',"import pathlib,time; time.sleep(.3); pathlib.Path('model_done').write_text('done')"],check=True)
'''
def load():
    s=importlib.util.spec_from_file_location('isolated_installer',installer)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def await_file(p):
    until=time.monotonic()+5
    while not p.exists():
        assert time.monotonic()<until
        time.sleep(.01)
for case in ('final_tick_and_gate','replacement_before_gate'):
    with tempfile.TemporaryDirectory(prefix='wms676-review-process-') as td:
        app=Path(td); pkg=app/'support_agent'; pkg.mkdir()
        (pkg/'__init__.py').write_text(''); (pkg/'__main__.py').write_text(WORKER)
        m=load(); m.APP=app; m.ROOT=app; m.PLIST=app/'unused.plist'; m.DRAIN_TIMEOUT_SEC=5
        procs=[]; old=subprocess.Popen([sys.executable,'-B','-m','support_agent'],cwd=app)
        procs.append(old); await_file(app/'starts'); old_pid=old.pid; gate=None
        try:
            if case=='replacement_before_gate':
                old.terminate(); old.wait(timeout=5)
                (app/'model_done').unlink(); (app/'starts').unlink()
                replacement=subprocess.Popen([sys.executable,'-B','-m','support_agent'],cwd=app)
                procs.append(replacement); await_file(app/'starts')
                m.service_pid=lambda: replacement.pid
            else:
                m.service_pid=lambda: old.pid
            def rows():
                global gate
                old.poll()
                if case=='final_tick_and_gate' and old.returncode is not None and gate is None:
                    gate=subprocess.Popen([sys.executable,'-B','-m','support_agent'],cwd=app)
                    procs.append(gate); time.sleep(.08)
                return {int(x.split()[0]):int(x.split()[1]) for x in
                        subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines() if x.strip()}
            m.process_tree=rows
            def bootout(args,**kw):
                assert args[:2]==['launchctl','bootout']
                if case=='replacement_before_gate':
                    assert replacement.poll() is None
                    print('REAL_PROCESS_REPRO: bootout reached while replacement worker alive; old PID was reaped before gate')
                    raise RuntimeError('unsafe bootout intercepted; no actual launchctl call')
                assert old.poll()==0 and (app/'model_done').read_text()=='done'
                assert gate.poll() is None and (app/'starts').read_text()=='worker\n'
                gate.terminate(); gate.wait(timeout=3)
                print('REAL_PROCESS_PASS: final-tick model completed; old worker exited; -m support_agent gate started no second worker')
                return SimpleNamespace(returncode=0)
            m.subprocess=SimpleNamespace(run=bootout)
            try: m.drain_and_bootout(old_pid)
            except RuntimeError as e:
                assert case=='replacement_before_gate' and 'unsafe bootout' in str(e)
            assert (pkg/'__main__.py').read_text()==WORKER
        finally:
            for p in procs:
                if p.poll() is None: p.terminate()
            for p in procs: p.wait(timeout=5)
```

### F2: настоящий ребёнок отделяется до первого снимка

```python
import importlib.util, os, subprocess, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace

path=Path('docs/reviews/artifacts/wms-676/install_sol61.py').resolve()
spec=importlib.util.spec_from_file_location('isolated_installer',path)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix='wms676-review-orphan-') as td:
    app=Path(td); pkg=app/'support_agent'; pkg.mkdir()
    (pkg/'__init__.py').write_text('')
    (pkg/'__main__.py').write_text('''import os, pathlib, signal, subprocess, sys, time
stop=False
def term(*_):
    global stop
    stop=True
signal.signal(signal.SIGTERM,term)
pathlib.Path('ready').write_text('yes')
while not stop: time.sleep(.001)
child=subprocess.Popen([sys.executable,'-c',"import pathlib,time; time.sleep(1); pathlib.Path('done').write_text('yes')"])
pathlib.Path('child_pid').write_text(str(child.pid))
os._exit(0)
''')
    parent=subprocess.Popen([sys.executable,'-B','-m','support_agent'],cwd=app)
    deadline=time.monotonic()+5
    while not (app/'ready').exists():
        assert time.monotonic()<deadline; time.sleep(.01)
    m.APP=app; m.PLIST=app/'unused.plist'; m.service_pid=lambda:parent.pid
    def rows():
        parent.wait(timeout=3)
        return {int(x.split()[0]):int(x.split()[1]) for x in
                subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines() if x.strip()}
    m.process_tree=rows
    def intercept(args,**kwargs):
        child=int((app/'child_pid').read_text()); os.kill(child,0)
        assert not (app/'done').exists() and rows()[child]==1
        print('REAL_ORPHAN_REPRO: bootout requested while never-observed final-tick child is alive with PPID=1')
        raise RuntimeError('unsafe bootout intercepted')
    m.subprocess=SimpleNamespace(run=intercept)
    try: m.drain_and_bootout(parent.pid)
    except RuntimeError as e: assert str(e)=='unsafe bootout intercepted'
    finally:
        deadline=time.monotonic()+5
        while not (app/'done').exists():
            assert time.monotonic()<deadline; time.sleep(.01)
    print('SYNTHETIC_CHILD_NATURALLY_FINISHED; real launchctl and TG never called')
```

### F3: изменение checkout после предварительной проверки

```python
import importlib.util, json, sys, tempfile
from pathlib import Path
import pytest

root=Path.cwd(); sys.path.insert(0,str(root/'tools/support_agent'))
spec=importlib.util.spec_from_file_location('installer_contract',root/'tools/support_agent/tests/test_install_model_migration.py')
t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
with tempfile.TemporaryDirectory(prefix='wms676-review-source-') as td, pytest.MonkeyPatch.context() as mp:
    h=t.installation.__wrapped__(Path(td),mp)
    original=h.module.drain_and_bootout
    def changed_during_drain(pid):
        original(pid)
        (h.module.ROOT/'tools/support_agent/support_agent/worker.py').write_bytes(b'# UNPUBLISHED concurrent editor bytes\n')
    mp.setattr(h.module,'drain_and_bootout',changed_during_drain)
    h.module.main()
    installed=(h.package/'worker.py').read_bytes()
    report=json.loads((h.module.ROOT/'docs/reviews/artifacts/wms-676/local-install.json').read_text())
    assert installed==b'# UNPUBLISHED concurrent editor bytes\n'
    assert report['all_package_modules_match_commit'] is True
    print('REPRO_SOURCE_RACE: unpublished bytes installed; all_package_modules_match_commit=True; installed_sha='+report['installed_sha'])
```

## Передача ведущему

R5 исправлен в проверенном кандидате. R8 остаётся технически нарушенным по трём
воспроизведённым основаниям. Product approval не закрывает эти дефекты. Требуются
исправления, проверки соответствующих окон гонки и независимое повторное ревью
нового опубликованного продуктового SHA. Только затем root отдельно решает вопрос
установки и подтверждает фактическую версию, сохранность состояния и реальный новый
вызов модели. Этот отчёт не является разрешением установки и не заявляет runtime PASS.
