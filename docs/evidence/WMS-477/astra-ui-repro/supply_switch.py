"""Три дефекта последнего ревью в настоящем Chrome: сохранённое «Повторить» из
прежней поставки, отброшенный ответ успешной операции и окно снятия Честного знака,
пережившее смену поставки.

Тот же компонент из проверяемого SHA, что и в reproduce.py, данные синтетические,
сеть перехвачена. Оснастка берётся из main.tsx рядом, у неё добавлены три умения,
которых там не было: перехват снятия требования Честного знака, ответ ошибкой,
по которой экран предлагает повтор, и собственное задание упаковки у каждой
поставки, чтение которого можно сорвать.

Без аргументов требует исправленного поведения. С --expect-vulnerable записывает
исходное поведение: так проверяется, что сценарии вообще различают эти состояния.
Исходное поведение снимается подменой самого экрана в рабочем дереве, поэтому HEAD
в такой прогон не меняется — что на самом деле выполнялось, говорит component_blob
в отчёте. Запускать из корня репозитория.
"""
import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expect-vulnerable', action='store_true',
                    help='Требовать исходные дефекты вместо исправленного поведения.')
args = parser.parse_args()

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PORT = int(os.environ.get('WMS_QA_PORT', '5579'))
FIXTURE = REPO / 'frontend/tmp/wms477-supply-switch'
OUT = HERE / 'local-switch'
FIXTURE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(exist_ok=True)

source = (HERE / 'main.tsx').read_text()
patches = [
    # Снятие требования Честного знака держится так же, как остальные запросы.
    ("(workspace|markings\\/sync|orders\\/batch)",
     "(workspace|markings\\/sync|orders\\/batch|honest-sign-skip)"),
    # Своё задание упаковки у каждой поставки: иначе смена поставки не меняет
    # зависимости эффекта и его чтение не повторяется.
    ("packaging_task_id: 'fixture-task'",
     "packaging_task_id: `fixture-task-${supplyId}`"),
    ("let latency = 0",
     "let latency = 0\nlet brokenPackagingTask: string | null = null"),
    # Ошибка чтения задания приходит мимо run(): именно она в разборе Astra
    # показывала оператору чужую кнопку «Повторить».
    ("  if (url.includes('/operations/packaging-tasks/fixture-task')) return response({id:'fixture-task',",
     "  if (brokenPackagingTask && url.includes(`/operations/packaging-tasks/${brokenPackagingTask}`))\n"
     "    return new Response(JSON.stringify({ detail: 'QA: задание упаковки недоступно' }),"
     " { status: 503, headers: { 'Content-Type': 'application/json' } })\n"
     "  if (url.includes('/operations/packaging-tasks/fixture-task')) return response({id:'fixture-task',"),
    (";(window as any).qa = {\n  log, resolve: resolveRequest,",
     """function failRequest(id: number, retryable: boolean) {
  const callback = pending.get(id)
  if (!callback) throw new Error(`Pending request ${id} missing`)
  pending.delete(id)
  log.push({ event: 'failure', id, retryable, at: Date.now() })
  callback(new Response(
    JSON.stringify({ detail: { code: 'qa_failure', message: 'QA: внешняя система не ответила', retryable } }),
    { status: 502, headers: { 'Content-Type': 'application/json' } },
  ))
}
;(window as any).qa = {
  log, resolve: resolveRequest, fail: failRequest,
  breakPackagingTask: (value: string | null) => { brokenPackagingTask = value },"""),
]
fixture_source = source
for old, new in patches:
    replaced = fixture_source.replace(old, new)
    assert replaced != fixture_source, f'не удалось применить правку оснастки: {old[:60]}'
    fixture_source = replaced
(FIXTURE / 'main.tsx').write_text(fixture_source)
(FIXTURE / 'index.html').write_text(
    '<!doctype html><html lang="ru"><meta charset="UTF-8"><div id="root"></div>'
    '<script type="module" src="/tmp/wms477-supply-switch/main.tsx"></script></html>'
)

log = (OUT / 'vite.log').open('w')
server = subprocess.Popen(
    ['./node_modules/.bin/vite', '--host', '127.0.0.1', '--port', str(PORT), '--strictPort'],
    cwd=REPO / 'frontend', stdout=log, stderr=subprocess.STDOUT,
)
results = {'sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
           'component_blob': subprocess.check_output(
               ['git', 'hash-object', 'frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx'],
               cwd=REPO, text=True).strip(),
           'mode': 'expect-vulnerable' if args.expect_vulnerable else 'expect-fixed',
           'scenarios': {}, 'page_errors': [], 'failed': []}
try:
    for _ in range(200):
        if server.poll() is not None:
            raise RuntimeError((OUT / 'vite.log').read_text())
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/tmp/wms477-supply-switch/index.html')
            break
        except OSError:
            time.sleep(0.1)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)

        def fresh():
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: results['page_errors'].append(str(error)))
            page.clock.install()
            page.goto(f'http://127.0.0.1:{PORT}/tmp/wms477-supply-switch/index.html', wait_until='networkidle')
            page.locator('[data-order-id="A1"]').wait_for()
            return page

        def tick(page, ms):
            page.clock.run_for(ms)
            page.wait_for_timeout(30)

        def alerts(page):
            return ' | '.join(page.locator('.MuiAlert-root').all_inner_texts())

        def rows(page):
            return page.locator('[data-order-id]').all_inner_texts()

        def last_pending(page):
            return page.evaluate('window.qa.pending().at(-1) ?? null')

        def open_b(page):
            page.click('#open-B')
            page.locator('[data-order-id="B1"]').wait_for()
            page.wait_for_timeout(150)

        def verify(name, bug, fixed, data):
            data['bug_reproduced'] = bug
            data['fixed_behaviour'] = fixed
            expected = bug if args.expect_vulnerable else fixed
            data['expectation_met'] = expected
            if not expected:
                results['failed'].append(name)
            results['scenarios'][name] = data
            print(name, json.dumps(data, ensure_ascii=False), flush=True)

        # 1. Ошибка с возможностью повтора возникла в A. Оператор ушёл в B, где
        # сорвалось чтение задания упаковки — ошибка мимо run(), поэтому прежний
        # повтор она не стирает. Кнопка «Повторить» рядом с ошибкой B отправила бы
        # операцию поставки A, а её ответ лёг бы на состав B.
        page = fresh()
        page.locator('[data-testid="fbs-packing-check-wb"]').click()
        page.wait_for_timeout(100)
        manual_a = last_pending(page)
        page.evaluate('id=>window.qa.fail(id,true)', manual_a)
        page.get_by_role('button', name='Повторить').wait_for()
        retry_in_a = page.get_by_role('button', name='Повторить').count()
        page.evaluate('window.qa.breakPackagingTask("fixture-task-B")')
        open_b(page)
        page.wait_for_timeout(250)
        error_in_b = alerts(page)
        retry_beside_b_error = page.get_by_role('button', name='Повторить').count()
        requests_before_click = len(page.evaluate('window.qa.log'))
        rows_after_click = rows(page)
        sent_a_operation = False
        if retry_beside_b_error:
            page.get_by_role('button', name='Повторить').click()
            page.wait_for_timeout(200)
            new_events = page.evaluate('window.qa.log')[requests_before_click:]
            sent_a_operation = any(e['event'] == 'request' and e.get('supply') == 'A' for e in new_events)
            held = last_pending(page)
            if held is not None:
                page.evaluate('id=>window.qa.resolve(id,"A","accepted")', held)
                page.wait_for_timeout(250)
            rows_after_click = rows(page)
        page.screenshot(path=str(OUT / 'retry.png'), full_page=True)
        verify('saved_retry_does_not_survive_supply_switch',
               bug=retry_in_a == 1 and retry_beside_b_error == 1 and sent_a_operation
               and any('Товар поставки A' in row for row in rows_after_click),
               fixed=retry_in_a == 1 and retry_beside_b_error == 0
               and 'задание упаковки' in error_in_b
               and all('Товар поставки B' in row for row in rows_after_click),
               data={'retry_in_a': retry_in_a, 'retry_beside_b_error': retry_beside_b_error,
                     'error_in_b': error_in_b, 'sent_a_operation': sent_a_operation,
                     'rows': rows_after_click})
        page.close()

        # 2. Тихое чтение стартовало позже ручной проверки, но прочитало базу до
        # её записи. Свой снимок операция не применяет, зато просит новое чтение —
        # оно начинается после записи, поэтому строка доходит до правды. Итог
        # «подтверждено X из Y» считается по ответу, поэтому его называет тот же
        # восстановительный снимок: по отброшенному счёт спорил бы со строками.
        page = fresh()
        page.locator('[data-testid="fbs-packing-check-wb"]').click()
        page.wait_for_timeout(100)
        manual = last_pending(page)
        tick(page, 15000)
        stale_get = last_pending(page)
        assert stale_get != manual, 'тихое обновление не стартовало после действия'
        page.evaluate('id=>window.qa.resolve(id,"A","pending")', stale_get)
        page.wait_for_timeout(100)
        before_recovery = rows(page)
        page.evaluate('id=>window.qa.resolve(id,"A","accepted")', manual)
        page.wait_for_timeout(250)
        after_discard = rows(page)
        notice_after_discard = alerts(page)
        recovery = last_pending(page)
        recovery_started = recovery is not None and recovery not in (manual, stale_get)
        if recovery_started:
            page.evaluate('id=>window.qa.resolve(id,"A","accepted")', recovery)
            page.wait_for_timeout(250)
        final = rows(page)
        notice_after_recovery = alerts(page)
        check_button_ready = page.locator('[data-testid="fbs-packing-check-wb"]').is_enabled()
        page.screenshot(path=str(OUT / 'recovery.png'), full_page=True)
        verify('lost_race_is_repaired_by_a_read_started_after_the_write',
               bug=not recovery_started and all('WB ещё не подтвердил ЧЗ' in row for row in final),
               fixed=recovery_started
               and all('WB ещё не подтвердил ЧЗ' in row for row in after_discard)
               and all('ЧЗ принят WB' in row for row in final)
               and 'Проверено в WB' not in notice_after_discard
               and 'Проверено в WB: подтверждено 1 из 1.' in notice_after_recovery
               and check_button_ready,
               data={'before_recovery': before_recovery, 'after_discard': after_discard,
                     'recovery_started': recovery_started, 'final': final,
                     'notice_after_discard': notice_after_discard,
                     'notice_after_recovery': notice_after_recovery,
                     'check_button_ready': check_button_ready,
                     'log': page.evaluate('window.qa.log')})
        page.close()

        # 3. Подтверждённое снятие требования в A и уход в B до ответа. Ответ A
        # принадлежит её открытию, но окно и занятость — состоянию экрана: иначе
        # у диалога отключены обе кнопки и закрытие, и выхода нет.
        page = fresh()
        page.locator('[data-testid="fbs-skip-honest-sign"]').click()
        page.locator('[data-testid="fbs-skip-honest-sign-confirm"]').click()
        page.wait_for_timeout(100)
        skip_a = last_pending(page)
        dialog_in_a = page.locator('[data-testid="fbs-skip-honest-sign-confirm"]').count()
        open_b(page)
        page.evaluate('id=>window.qa.resolve(id,"A","pending")', skip_a)
        tick(page, 1000)
        page.wait_for_timeout(250)
        confirm = page.locator('[data-testid="fbs-skip-honest-sign-confirm"]')
        dialog_after_answer = confirm.count()
        cancel = page.get_by_role('button', name='Отмена')
        stuck = bool(dialog_after_answer) and not confirm.first.is_enabled() and not cancel.first.is_enabled()
        reopened = False
        closed_again = dialog_after_answer
        trigger = page.locator('[data-testid="fbs-skip-honest-sign"]')
        trigger_enabled = trigger.is_enabled() if trigger.count() else False
        if not dialog_after_answer and trigger_enabled:
            # Окно снова открывается и закрывается обычным способом — не заперто.
            trigger.click()
            reopened = confirm.is_enabled()
            page.get_by_role('button', name='Отмена').click()
            tick(page, 1000)
            page.wait_for_timeout(150)
            closed_again = confirm.count()
        page.screenshot(path=str(OUT / 'skip-dialog.png'), full_page=True)
        verify('skip_honest_sign_dialog_is_not_stuck_after_a_supply_switch',
               bug=dialog_in_a == 1 and stuck,
               fixed=dialog_in_a == 1 and dialog_after_answer == 0 and trigger_enabled
               and reopened and closed_again == 0
               and all('Товар поставки B' in row for row in rows(page)),
               data={'dialog_in_a': dialog_in_a, 'dialog_after_answer': dialog_after_answer,
                     'stuck_without_exit': stuck, 'trigger_enabled': trigger_enabled,
                     'reopened_confirm_enabled': reopened, 'closed_again': closed_again,
                     'rows': rows(page)})
        page.close()

        browser.close()
    assert not results['page_errors'], results['page_errors']
    assert not results['failed'], f"{results['mode']} failed: {results['failed']}"
finally:
    (OUT / 'result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    log.close()
