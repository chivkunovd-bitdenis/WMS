import base64
import io
import json
from pathlib import Path
import sqlite3
import sys
import threading
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wms_print_agent as agent
import wms_print_direct
from wms_print_direct import (
    DefaultWindowsAdapter, DirectServer, Handler, PrintNotSent, Printer,
    acquire_instance, default_printer, fit_layout, flatten_png, main, running_instance)

try:
    from PIL import Image
except ImportError:  # the Windows package always has Pillow
    Image = None

PNG = b'\x89PNG\r\n\x1a\n' + b'test'

def job(key='scan-1', data=PNG, width=58, height=40):
    return {
        'idempotencyKey': key,
        'imageDataUrl': 'data:image/png;base64,' + base64.b64encode(data).decode(),
        'widthMm': width,
        'heightMm': height,
    }


class DirectPrintTest(unittest.TestCase):
    def test_both_production_domains_can_reach_local_printer(self):
        handler = object.__new__(Handler)
        handler.server = Mock(server_port=17843)
        for origin in ('https://sellerfocus.pro', 'https://wms.sellerfocus.pro'):
            handler.headers = {'Host': '127.0.0.1:17843', 'Origin': origin}
            self.assertTrue(handler.allowed())
        handler.headers['Origin'] = 'https://unrelated.example'
        self.assertFalse(handler.allowed())

    def test_receipt_survives_restart_without_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock(return_value='printer-123')
            self.assertEqual(Printer(Path(root), submit).print(job()), 'printer-123')
            self.assertEqual(Printer(Path(root), submit).print(job()), 'printer-123')
            submit.assert_called_once()

    def test_uncertain_submission_not_repeated(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock(side_effect=RuntimeError('lost receipt'))
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    Printer(Path(root), submit).print(job())
            submit.assert_called_once()

    def test_changed_content_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock(return_value='printer-123')
            printer = Printer(Path(root), submit)
            printer.print(job())
            with self.assertRaises(ValueError):
                printer.print(job(data=PNG+b'changed'))
            submit.assert_called_once()

    def test_changed_size_is_part_of_idempotent_job(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock(return_value='printer-123')
            printer = Printer(Path(root), submit)
            printer.print(job())
            with self.assertRaises(ValueError):
                printer.print(job(width=60))
            submit.assert_called_once()

    def test_missing_or_invalid_size_never_reaches_printer(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock()
            invalid = job()
            del invalid['widthMm']
            with self.assertRaisesRegex(ValueError, 'размер'):
                Printer(Path(root), submit).print(invalid)
            with self.assertRaisesRegex(ValueError, 'размер'):
                Printer(Path(root), submit).print(job(width=True))
            submit.assert_not_called()

    def test_identity_formula_is_the_installed_one(self):
        # Journals written by the installed Windows release must still be recognised.
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            printer = Printer(Path(root), Mock(return_value='x'))
            printer.print(job())
            row = printer._lookup('scan-1')
            self.assertEqual(row[0], hashlib.sha256(PNG + b'|580x400').hexdigest())

    def test_windows_health_and_print_resolve_the_system_default_printer(self):
        win32print = SimpleNamespace(GetDefaultPrinter=Mock(return_value='Xprinter XP-420B'))
        with (
            patch('wms_print_direct.sys.platform', 'win32'),
            patch.dict(sys.modules, {'win32print': win32print}),
        ):
            self.assertEqual(default_printer(), 'Xprinter XP-420B')
        win32print.GetDefaultPrinter.assert_called_once_with()

    def test_invalid_content_never_reaches_printer(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock()
            with self.assertRaises(ValueError):
                Printer(Path(root), submit).print(job(data=b'not a png'))
            submit.assert_not_called()

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.subprocess.Popen')
    @patch('wms_print_direct.subprocess.run')
    @patch('wms_print_direct.running_instance', return_value=(wms_print_direct.BUILD, True))
    @patch('wms_print_direct.acquire_instance', return_value=True)
    @patch('wms_print_direct.Printer')
    @patch('wms_print_direct.DirectServer')
    def test_start_and_reopen_never_launch_browser(self, server, printer, acquire, running, run, popen):
        main()
        server.return_value.serve_forever.assert_called_once()
        server.side_effect = OSError('already running')
        main()  # the port belongs to a live WMS Print: quiet success
        run.assert_not_called()
        popen.assert_not_called()

    @patch('wms_print_direct.sys.platform', 'darwin')
    @patch('wms_print_direct.subprocess.run')
    def test_macos_default_uses_stable_locale(self, run):
        run.return_value.stdout = 'system default destination: Label_Printer\n'
        self.assertEqual(default_printer(), 'Label_Printer')
        self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')


def png(color=(0, 0, 0, 255), size=(8, 4), mode='RGBA'):
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, 'PNG')
    return out.getvalue()


class FakeAdapter:
    """Stands in for the OS adapter: fails before or after the boundary."""
    def __init__(self, before=None, after=None):
        self.before, self.after, self.calls = before, after, 0

    def default(self):
        return 'Label'

    def submit_default(self, data, queue, mark, width_mm=None, height_mm=None):
        self.calls += 1
        if self.before:
            raise self.before
        mark()
        if self.after:
            raise self.after
        return 'Label-7'


class RetryBoundaryTest(unittest.TestCase):
    def printer(self, root, adapter):
        with patch('wms_print_direct.MacPrinter'), patch('wms_print_direct.DefaultWindowsAdapter'):
            printer = Printer(Path(root), print_timeout=2, minimum_to_start=0)
        printer.adapter = adapter
        return printer

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_failure_before_the_os_boundary_allows_retry_of_same_key(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = FakeAdapter(before=ValueError('cannot prepare'))
            printer = self.printer(root, adapter)
            with self.assertRaises(ValueError):
                printer.print(job())
            adapter.before = None
            self.assertEqual(printer.print(job()), 'Label-7')
            self.assertEqual(adapter.calls, 2)

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_proven_not_sent_after_mark_removes_the_mark(self):
        with tempfile.TemporaryDirectory() as root:
            printer = self.printer(root, FakeAdapter())
            printer.submit = Mock(side_effect=[PrintNotSent('lp did not start'), 'Label-9'])
            with self.assertRaises(PrintNotSent):
                printer.print(job())
            self.assertEqual(printer.print(job()), 'Label-9')

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_failure_after_the_boundary_is_never_repeated(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = FakeAdapter(after=agent.UnknownPrintOutcome('lost'))
            printer = self.printer(root, adapter)
            for _ in range(2):
                with self.assertRaises(agent.UnknownPrintOutcome):
                    printer.print(job())
            self.assertEqual(adapter.calls, 1)

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_hung_driver_answers_in_time_and_does_not_block_forever(self):
        release = threading.Event()
        entered = Mock()

        def hang(data):
            entered()
            release.wait(10)
            return 'late-1'

        with tempfile.TemporaryDirectory() as root:
            printer = Printer(Path(root), hang, print_timeout=0.4, minimum_to_start=0)
            started = time.monotonic()
            with self.assertRaises(agent.UnknownPrintOutcome) as unknown:
                printer.print(job('a'))
            self.assertIn('Принтер не отвечает. Перезапустите WMS Print', str(unknown.exception))
            # a new key is refused within its own deadline, unmarked and not sent
            with self.assertRaises(PrintNotSent) as refused:
                printer.print(job('b', PNG + b'2'))
            self.assertIn('не отвечает', str(refused.exception))
            self.assertIn('не отправлялось', str(refused.exception))
            # the key that may be going out is never called "not sent": history is read first
            asked = time.monotonic()
            with self.assertRaises(agent.UnknownPrintOutcome) as again:
                printer.print(job('a'))
            self.assertLess(time.monotonic() - asked, 0.2)
            self.assertIn('Проверьте принтер', str(again.exception))
            self.assertNotIn('не отправлялось', str(again.exception))
            self.assertLess(time.monotonic() - started, 3)
            entered.assert_called_once()
            release.set()
            for _ in range(100):  # the late receipt is recorded for the same key
                try:
                    if printer.print(job('a')) == 'late-1':
                        break
                except agent.UnknownPrintOutcome:
                    time.sleep(0.05)
            self.assertEqual(printer.print(job('a')), 'late-1')
            printer.submit = Mock(return_value='b-1')
            self.assertEqual(printer.print(job('b', PNG + b'2')), 'b-1')

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_job_stuck_before_the_boundary_cannot_start_late(self):
        release = threading.Event()
        calls = []

        class Slow(FakeAdapter):
            def submit_default(self, data, queue, mark, width_mm=None, height_mm=None):
                self.calls += 1
                release.wait(10)      # e.g. a driver call that hangs while preparing
                mark()                # too late: the browser has been told "not sent"
                calls.append('sent')
                return 'Label-1'

        with tempfile.TemporaryDirectory() as root:
            adapter = Slow()
            printer = self.printer(root, adapter)
            printer.print_timeout = 0.4
            with self.assertRaises(PrintNotSent) as raised:
                printer.print(job())
            self.assertIn('не отправлялось', str(raised.exception))
            release.set()
            for _ in range(100):
                if not printer.hung and printer.slot.acquire(blocking=False):
                    printer.slot.release()
                    break
                time.sleep(0.05)
            self.assertEqual(calls, [])  # nothing went out
            self.assertIsNone(printer._lookup('scan-1'))  # key is free
            printer.print_timeout = 5
            release.set()
            adapter.submit_default = lambda data, queue, mark, w=None, h=None: (mark(), 'Label-2')[1]
            self.assertEqual(printer.print(job()), 'Label-2')

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_too_little_time_left_never_starts_a_job(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = FakeAdapter()
            printer = self.printer(root, adapter)
            printer.minimum_to_start = 100
            with self.assertRaises(PrintNotSent):
                printer.print(job())
            self.assertEqual(adapter.calls, 0)


class ParallelAndBudgetTest(unittest.TestCase):
    printer = RetryBoundaryTest.printer

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_parallel_repeat_while_first_is_processing_hears_in_progress(self):
        class Slow(FakeAdapter):
            def submit_default(self, data, queue, mark, width_mm=None, height_mm=None):
                time.sleep(0.8)   # still preparing: nothing is marked yet
                mark()
                return 'Label-5'

        with tempfile.TemporaryDirectory() as root:
            printer = self.printer(root, Slow())
            first = threading.Thread(target=lambda: printer.print(job()))
            first.start()
            time.sleep(0.2)
            with self.assertRaises(agent.UnknownPrintOutcome) as raised:
                printer.print(job())
            self.assertIn('в работе', str(raised.exception))
            self.assertNotIn('не отправлялось', str(raised.exception))
            first.join()
            self.assertEqual(printer.print(job()), 'Label-5')

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_budget_spent_waiting_for_the_journal_means_not_sent_and_mark_removed(self):
        with tempfile.TemporaryDirectory() as root:
            sent = []

            class Locking(FakeAdapter):
                def default(inner):
                    blocker = sqlite3.connect(Path(root) / 'direct-jobs.sqlite3', timeout=1, check_same_thread=False)
                    blocker.execute('BEGIN EXCLUSIVE')
                    threading.Timer(0.9, lambda: (blocker.commit(), blocker.close())).start()
                    return 'Label'

                def submit_default(inner, data, queue, mark, width_mm=None, height_mm=None):
                    mark()
                    sent.append(1)
                    return 'Label-1'

            printer = self.printer(root, Locking())
            printer.print_timeout, printer.minimum_to_start = 1.2, 0.5
            with self.assertRaises(PrintNotSent) as raised:
                printer.print(job())
            self.assertIn('не отправлялось', str(raised.exception))
            self.assertEqual(sent, [])
            for _ in range(200):   # the worker removes the mark right after the answer left
                if printer._lookup('scan-1') is None:
                    break
                time.sleep(0.05)
            printer.print_timeout, printer.minimum_to_start = 5, 0.5
            if printer._lookup('scan-1') is None:      # normal case: the mark was removed, the key is free
                self.assertEqual(printer.print(job()), 'Label-1')
            else:   # the cleanup met a locked journal (slow machine): the key stays blocked, never freed
                with self.assertRaises(agent.UnknownPrintOutcome):
                    printer.print(job())
                self.assertEqual(sent, [])


class JournalBudgetAndIdentityTest(unittest.TestCase):
    printer = RetryBoundaryTest.printer

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_two_requests_competing_for_a_locked_journal_still_answer_in_time(self):
        with tempfile.TemporaryDirectory() as root:
            events = {}

            class Preparing(FakeAdapter):
                def default(inner):
                    if not events.get('a'):
                        events['a'] = True
                        time.sleep(1.0)   # preparation of request A, before its mark
                    return 'Label'

                def submit_default(inner, data, queue, mark, width_mm=None, height_mm=None):
                    mark()
                    return 'Label-1'

            printer = self.printer(root, Preparing())
            printer.print_timeout, printer.minimum_to_start = 2.0, 0.3
            answers = {}

            def request(name, key):
                started = time.monotonic()
                try:
                    answers[name] = printer.print(job(key, PNG + key.encode()))
                except Exception as exc:  # noqa: BLE001
                    answers[name] = exc
                answers[name + '_t'] = time.monotonic() - started

            a = threading.Thread(target=request, args=('a', 'ka'))
            a.start()
            time.sleep(0.15)   # A has passed its history check and is preparing
            blocker = sqlite3.connect(Path(root) / 'direct-jobs.sqlite3', timeout=1, check_same_thread=False)
            blocker.execute('BEGIN EXCLUSIVE')
            time.sleep(0.5)    # t = 0.65 s: B enters the journal and waits for SQLite
            b = threading.Thread(target=request, args=('b', 'kb'))
            b.start()
            a.join(5)
            b.join(5)
            blocker.rollback()
            blocker.close()
            self.assertIsInstance(answers['a'], PrintNotSent)           # A mark: lock wait ended with its budget
            self.assertLess(answers['a_t'], 2.0 + 1.5)                  # answered within its own deadline
            self.assertIsInstance(answers['b'], PrintNotSent)
            self.assertLess(answers['b_t'], 2.0 + 1.5)
            self.assertIsNone(printer._lookup('ka'))                    # both keys are free
            self.assertIsNone(printer._lookup('kb'))
            printer.print_timeout = 5
            self.assertEqual(printer.print(job('ka', PNG + b'ka')), 'Label-1')

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_known_identity_forms_are_accepted_and_rewritten_for_the_previous_version(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            printer = self.printer(root, FakeAdapter())
            python_form = hashlib.sha256(PNG + b'|580x400').hexdigest()
            rows = {
                'swift-key': hashlib.sha256(PNG + b'|58.0x40.0').hexdigest(),
                'oldest-key': hashlib.sha256(PNG).hexdigest(),
                'python-key': python_form,
            }
            with closing_db(Path(root) / 'direct-jobs.sqlite3') as db:
                for key, digest in rows.items():
                    db.execute('INSERT INTO jobs VALUES (?, ?, ?)', (key, digest, 'R-' + key))
                db.commit()
            for key in rows:
                self.assertEqual(printer.print(job(key)), 'R-' + key)
                self.assertEqual(printer._lookup(key)[0], python_form)   # what 1bdd6cdf reads
            self.assertEqual(printer.adapter.calls, 0)
            with self.assertRaises(ValueError):
                printer.print(job('swift-key', width=60))


def closing_db(path):
    from contextlib import closing
    return closing(sqlite3.connect(path))


class CleanupAndUnsentTest(unittest.TestCase):
    printer = RetryBoundaryTest.printer

    @staticmethod
    def _quiet(printer, body):
        try:
            printer.print(body)
        except Exception:  # noqa: BLE001
            pass

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_waiting_for_the_slot_answers_in_time_even_if_the_journal_lock_is_held(self):
        release = threading.Event()
        with tempfile.TemporaryDirectory() as root:
            printer = Printer(Path(root), lambda data: release.wait(10) and 'r', print_timeout=1.0, minimum_to_start=0.1)
            first = threading.Thread(target=lambda: self._quiet(printer, job('first', PNG + b'1')), daemon=True)
            first.start()
            time.sleep(0.2)               # `first` holds the slot
            answers = {}

            def waiting():
                started = time.monotonic()
                try:
                    printer.print(job('w', PNG + b'w'))
                except Exception as exc:  # noqa: BLE001
                    answers['w'] = exc
                answers['t'] = time.monotonic() - started

            waiter = threading.Thread(target=waiting)
            waiter.start()
            time.sleep(0.3)
            printer.lock.acquire()        # another request sits in the journal for a long time
            waiter.join(4)
            printer.lock.release()
            self.assertIsInstance(answers['w'], PrintNotSent)
            self.assertLess(answers['t'], 1.0 + 0.4)   # the answer did not wait for the lock
            release.set()
            first.join(3)
            printer.submit = Mock(return_value='w-1')
            printer.print_timeout = 5
            self.assertEqual(printer.print(job('w', PNG + b'w')), 'w-1')   # the key was released later

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_mark_that_could_not_be_removed_keeps_the_key_blocked_also_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            class Refused(FakeAdapter):
                def submit_default(inner, data, queue, mark, width_mm=None, height_mm=None):
                    inner.calls += 1
                    mark()
                    raise PrintNotSent('lp did not start')

            adapter = Refused()
            printer = self.printer(root, adapter)
            original = printer._execute

            def locked_delete(sql, params=(), *args, **kwargs):
                if sql.startswith('DELETE'):
                    raise sqlite3.OperationalError('database is locked')
                return original(sql, params, *args, **kwargs)

            with patch.object(printer, '_execute', side_effect=locked_delete):
                with self.assertRaises(PrintNotSent):
                    printer.print(job())
            with self.assertRaises(agent.UnknownPrintOutcome) as same_run:   # nothing frees the key
                printer.print(job())
            self.assertIn('Проверьте принтер', str(same_run.exception))
            restarted = self.printer(root, Refused())
            with self.assertRaises(agent.UnknownPrintOutcome):
                restarted.print(job())
            self.assertEqual(adapter.calls + restarted.adapter.calls, 1)     # one key, one send

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_error_lost_result_restart_repeat_sends_exactly_once(self):
        """R5-01: the receipt cannot be written after the job went out; a restart must not resend."""
        with tempfile.TemporaryDirectory() as root:
            adapter = FakeAdapter()
            printer = self.printer(root, adapter)
            original = printer._execute

            def no_receipt(sql, params=(), *args, **kwargs):
                if sql.startswith('UPDATE'):
                    raise sqlite3.OperationalError('database is locked')
                return original(sql, params, *args, **kwargs)

            with patch.object(printer, '_execute', side_effect=no_receipt):
                self.assertEqual(printer.print(job()), 'Label-7')   # sent, the answer reached the browser
            for _ in range(2):                                      # repeat in the run and after restarts
                again = self.printer(root, FakeAdapter())
                with self.assertRaises(agent.UnknownPrintOutcome):
                    again.print(job())
                self.assertEqual(again.adapter.calls, 0)
            self.assertEqual(adapter.calls, 1)

    def test_no_direct_unsent_file_is_ever_written(self):
        with tempfile.TemporaryDirectory() as root:
            printer = Printer(Path(root), Mock(side_effect=PrintNotSent('x')))
            with self.assertRaises(PrintNotSent):
                printer.print(job())
            self.assertEqual(sorted(p.name for p in Path(root).iterdir()), ['direct-jobs.sqlite3'])

    @patch('wms_print_direct.sys.platform', 'darwin')
    def test_a_really_unknown_outcome_is_not_freed_by_restart(self):
        with tempfile.TemporaryDirectory() as root:
            printer = self.printer(root, FakeAdapter(after=agent.UnknownPrintOutcome('lost')))
            with self.assertRaises(agent.UnknownPrintOutcome):
                printer.print(job())
            again = self.printer(root, FakeAdapter())
            with self.assertRaises(agent.UnknownPrintOutcome):
                again.print(job())
            self.assertEqual(again.adapter.calls, 0)


class HealthTest(unittest.TestCase):
    def test_health_error_is_not_working(self):
        server = DirectServer(('127.0.0.1', 0), Handler)
        server.printer = Mock(hung=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            self.assertEqual(running_instance(server.server_port), (wms_print_direct.BUILD, False))
        finally:
            server.shutdown()
            server.server_close()

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.running_instance', return_value=(wms_print_direct.BUILD, False))
    @patch('wms_print_direct.acquire_instance', return_value=False)
    @patch('wms_print_direct.DirectServer')
    def test_second_start_does_not_call_a_failing_copy_working(self, server, acquire, running):
        with self.assertRaises(SystemExit) as stop:
            main()
        self.assertEqual(stop.exception.code, 1)
        server.assert_not_called()


class FakeDC:
    def __init__(self, area=(464, 320), dpi=(203, 203), events=None):
        self.area, self.dpi, self.events = area, dpi, events if events is not None else []

    def GetDeviceCaps(self, index):
        return {8: self.area[0], 10: self.area[1], 88: self.dpi[0], 90: self.dpi[1],
                110: self.area[0], 111: self.area[1]}[index]

    def StartDoc(self, name):
        self.events.append('StartDoc')
        return 5

    def StartPage(self): self.events.append('StartPage')
    def EndPage(self): self.events.append('EndPage')
    def EndDoc(self): self.events.append('EndDoc')
    def AbortDoc(self): self.events.append('AbortDoc')
    def DeleteDC(self): self.events.append('DeleteDC')
    def GetHandleOutput(self): return 1


@unittest.skipIf(Image is None, 'Pillow is required')
class WindowsAdapterTest(unittest.TestCase):
    def adapter(self, dc=None, dc_error=None):
        drawn = []

        class Dib:
            def __init__(self, image): self.image = image
            def draw(self, handle, box): drawn.append((self.image.size, box))

        adapter = DefaultWindowsAdapter(modules={'Image': Image, 'ImageWin': Mock(Dib=Dib)})
        adapter._create_sized_printer_dc = Mock(side_effect=dc_error, return_value=dc)
        return adapter, drawn

    def test_undecodable_png_fails_before_mark(self):
        mark = Mock()
        adapter, _ = self.adapter(FakeDC())
        with self.assertRaises(Exception):
            adapter.submit_default(b'\x89PNG\r\n\x1a\ntest', 'Q', mark, 58, 40)
        mark.assert_not_called()

    def test_driver_failure_fails_before_mark(self):
        mark = Mock()
        adapter, _ = self.adapter(dc_error=ValueError('driver refused'))
        with self.assertRaises(ValueError):
            adapter.submit_default(png(), 'Q', mark, 58, 40)
        mark.assert_not_called()

    def test_mark_is_set_right_before_start_doc(self):
        events = []
        adapter, drawn = self.adapter(FakeDC(events=events))
        self.assertEqual(adapter.submit_default(png(size=(58, 40)), 'Q', lambda: events.append('mark'), 58, 40), 'windows-5')
        self.assertEqual(events[:2], ['mark', 'StartDoc'])
        self.assertEqual(drawn[0][1], (0, 0, 464, 320))  # unchanged landscape-on-landscape fit

    def test_landscape_label_on_portrait_page_is_turned_and_larger(self):
        adapter, drawn = self.adapter(FakeDC(area=(320, 464)))
        adapter.submit_default(png(size=(580, 400)), 'Q', lambda: None, 40, 58)
        size, box = drawn[0]
        self.assertEqual(size, (400, 580))  # turned by 90 degrees
        self.assertEqual(box, (0, 0, 320, 464))

    def test_failure_after_start_doc_is_unknown_outcome(self):
        dc = FakeDC()
        dc.EndPage = Mock(side_effect=OSError('spooler'))
        adapter, _ = self.adapter(dc)
        with self.assertRaises(agent.UnknownPrintOutcome):
            adapter.submit_default(png(), 'Q', lambda: None, 58, 40)
        self.assertIn('AbortDoc', dc.events)


@unittest.skipIf(Image is None, 'Pillow is required')
class TransparencyTest(unittest.TestCase):
    def test_transparent_background_becomes_white_not_black(self):
        flat = flatten_png(Image, png((0, 0, 0, 0)))
        self.assertEqual(flat.mode, 'RGB')
        self.assertEqual(flat.getpixel((0, 0)), (255, 255, 255))

    def test_opaque_and_half_transparent_pixels(self):
        self.assertEqual(flatten_png(Image, png((0, 0, 0, 255))).getpixel((0, 0)), (0, 0, 0))
        gray = flatten_png(Image, png((0, 0, 0, 128))).getpixel((0, 0))
        self.assertTrue(120 <= gray[0] <= 135)

    def test_palette_transparency_and_plain_rgb(self):
        out = io.BytesIO()
        Image.new('P', (2, 2), 0).save(out, 'PNG', transparency=0)
        self.assertEqual(flatten_png(Image, out.getvalue()).getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(flatten_png(Image, png((1, 2, 3), mode='RGB')).getpixel((0, 0)), (1, 2, 3))

    def test_truncated_png_is_rejected(self):
        with self.assertRaises(Exception):
            flatten_png(Image, png()[:40])


class LayoutTest(unittest.TestCase):
    def test_square_pixels_keep_the_old_fit(self):
        self.assertEqual(fit_layout(580, 400, 464, 320, 203, 203), (False, 0, 0, 464, 320))
        self.assertEqual(fit_layout(300, 300, 464, 320, 203, 203), (False, 72, 0, 320, 320))

    def test_different_dpi_keeps_physical_proportions(self):
        rotate, x, y, w, h = fit_layout(100, 100, 406, 600, 203, 600)
        self.assertFalse(rotate)
        self.assertEqual((w, h), (203, 600))  # one inch by one inch, not a stretched shape

    def test_turned_only_when_clearly_larger(self):
        self.assertTrue(fit_layout(580, 400, 320, 464, 203, 203)[0])
        self.assertFalse(fit_layout(580, 400, 320, 330, 203, 203)[0])
        self.assertFalse(fit_layout(400, 400, 320, 464, 203, 203)[0])

    def test_bad_dpi_falls_back_to_square_pixels(self):
        self.assertEqual(fit_layout(580, 400, 464, 320, 0, None), (False, 0, 0, 464, 320))


class SingleInstanceTest(unittest.TestCase):
    @unittest.skipIf(sys.platform == 'win32', 'file lock is the macOS/Linux path')
    def test_second_lock_is_refused_and_released_with_the_first(self):
        with tempfile.TemporaryDirectory() as root:
            held = list(wms_print_direct._instance_guard)
            try:
                self.assertTrue(acquire_instance(Path(root)))
                self.assertFalse(acquire_instance(Path(root)))
                wms_print_direct._instance_guard.pop().close()
                self.assertTrue(acquire_instance(Path(root)))
            finally:
                for lock in wms_print_direct._instance_guard[len(held):]:
                    lock.close()
                wms_print_direct._instance_guard[:] = held

    def test_windows_named_mutex(self):
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 99
        with tempfile.TemporaryDirectory() as root, \
                patch('wms_print_direct.sys.platform', 'win32'), \
                patch('wms_print_direct.ctypes.WinDLL', create=True, return_value=kernel32), \
                patch('wms_print_direct.ctypes.get_last_error', create=True, return_value=183):
            self.assertFalse(acquire_instance(Path(root)))  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle.assert_called_once()
        with tempfile.TemporaryDirectory() as root, \
                patch('wms_print_direct.sys.platform', 'win32'), \
                patch('wms_print_direct.ctypes.WinDLL', create=True, return_value=kernel32), \
                patch('wms_print_direct.ctypes.get_last_error', create=True, return_value=0):
            held = list(wms_print_direct._instance_guard)
            self.assertTrue(acquire_instance(Path(root)))
            wms_print_direct._instance_guard[:] = held

    def test_port_cannot_be_shared_and_live_copy_is_recognised(self):
        first = DirectServer(('127.0.0.1', 0), Handler)
        port = first.server_port
        threading.Thread(target=first.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(OSError):
                DirectServer(('127.0.0.1', port), Handler)
            self.assertEqual(running_instance(port)[0], wms_print_direct.BUILD)
        finally:
            first.shutdown()
            first.server_close()

    def test_foreign_program_on_the_port_is_not_taken_for_ours(self):
        class Other(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({'app': 'something else'}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args): pass

        other = HTTPServer(('127.0.0.1', 0), Other)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        try:
            self.assertIsNone(running_instance(other.server_port))
        finally:
            other.shutdown()
            other.server_close()

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.running_instance', return_value=None)
    @patch('wms_print_direct.acquire_instance', return_value=True)
    @patch('wms_print_direct.DirectServer', side_effect=OSError('busy'))
    def test_foreign_port_owner_gives_a_clear_error_and_is_left_alone(self, server, acquire, running):
        with self.assertRaises(SystemExit) as stop:
            main()
        self.assertEqual(stop.exception.code, 1)

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.running_instance', return_value=(wms_print_direct.BUILD, True))
    @patch('wms_print_direct.acquire_instance', return_value=False)
    @patch('wms_print_direct.DirectServer')
    def test_second_copy_quietly_succeeds_when_first_is_alive(self, server, acquire, running):
        main()
        server.assert_not_called()

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.running_instance', return_value=('another-build', True))
    @patch('wms_print_direct.acquire_instance', return_value=False)
    @patch('wms_print_direct.DirectServer')
    def test_other_build_is_reported_and_left_running(self, server, acquire, running):
        with self.assertRaises(SystemExit) as stop:
            main()
        self.assertEqual(stop.exception.code, 1)
        server.assert_not_called()

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.running_instance', return_value=('', True))  # an older copy has no build id
    @patch('wms_print_direct.acquire_instance', return_value=True)
    @patch('wms_print_direct.DirectServer', side_effect=OSError('busy'))
    def test_older_copy_without_lock_is_another_build(self, server, acquire, running):
        with self.assertRaises(SystemExit):
            main()

    def test_build_id_comes_from_build_json_next_to_the_program(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'build.json').write_text(json.dumps({'source_commit': 'abc123'}))
            with patch('wms_print_direct.sys.executable', str(Path(root, 'wms-print'))):
                self.assertEqual(wms_print_direct.build_id(), 'abc123')
            with patch('wms_print_direct.sys.executable', '/nonexistent/python'), \
                    patch('wms_print_direct.__file__', str(Path(root, 'x.py'))):
                self.assertEqual(wms_print_direct.build_id(), 'abc123')


    @unittest.skipIf(Image is None, 'Pillow is required')
    def test_windows_custom_size_is_applied_to_one_job_devmode(self):
        calls = []

        class FakePrint:
            @staticmethod
            def OpenPrinter(queue):
                calls.append(('open', queue))
                return queue

            @staticmethod
            def GetPrinter(handle, level):
                self.assertEqual(level, 2)
                return {'pDevMode': SimpleNamespace(
                    PaperSize=9, PaperWidth=2100, PaperLength=2970,
                    Copies=2, Collate=1, Fields=0x00000002,
                )}

            @staticmethod
            def DocumentProperties(hwnd, handle, queue, output, input_, mode):
                calls.append((
                    'devmode', output.PaperSize, output.PaperWidth,
                    output.PaperLength, output.Copies, output.Fields,
                ))
                return 1

            @staticmethod
            def ClosePrinter(handle):
                calls.append(('close', handle))

        class FakeDc:
            def GetDeviceCaps(self, index):
                return {
                    8: 464, 10: 320, 88: 203, 90: 203,
                    110: 464, 111: 320, 112: 0, 113: 0,
                }[index]

            def StartDoc(self, title):
                calls.append(('start-doc', title))
                return 607

            def StartPage(self):
                calls.append(('start-page',))

            def GetHandleOutput(self):
                return 17

            def EndPage(self):
                calls.append(('end-page',))

            def EndDoc(self):
                calls.append(('end-doc',))

            def AbortDoc(self):
                calls.append(('abort',))

            def DeleteDC(self):
                calls.append(('delete-dc',))

        class FakeDib:
            def __init__(self, image):
                self.image = image

            def draw(self, handle, target):
                calls.append(('draw', handle, target))

        adapter = DefaultWindowsAdapter({
            'win32print': FakePrint,
            'win32gui': SimpleNamespace(CreateDC=lambda driver, queue, devmode: 17),
            'win32ui': SimpleNamespace(CreateDCFromHandle=lambda handle: FakeDc()),
            'Image': Image,
            'ImageWin': SimpleNamespace(Dib=FakeDib),
            'fitz': None,
        })

        self.assertEqual(
            adapter.submit_default(png(size=(464, 320)), 'Xprinter XP-420B', None, 58, 40),
            'windows-607',
        )
        devmode = next(call for call in calls if call[0] == 'devmode')
        self.assertEqual(devmode[1:5], (0, 580, 400, 1))
        self.assertEqual(devmode[5] & 0x00000002, 0)
        self.assertEqual(
            devmode[5] & (0x00000004 | 0x00000008 | 0x00000100),
            0x00000004 | 0x00000008 | 0x00000100,
        )
        self.assertIn(('draw', 17, (0, 0, 464, 320)), calls)
        self.assertNotIn(('abort',), calls)


class StandardCaseUnchangedTest(unittest.TestCase):
    """The layout of 1bdd6cdf for the normal 58x40 job must be bit-for-bit the same."""
    def test_equal_dpi_matches_the_installed_pixel_ratio_formula(self):
        for label_w, label_h in ((58, 40), (40, 58), (100, 150), (30, 20), (75, 120)):
            for dpi in (203, 300):
                page_w, page_h = round(label_w / 25.4 * dpi), round(label_h / 25.4 * dpi)
                for image_w, image_h in ((label_w * 10, label_h * 10), (page_w, page_h), (464, 320) if label_w > label_h else (320, 464)):
                    ratio = min(page_w / image_w, page_h / image_h)
                    w, h = max(1, round(image_w * ratio)), max(1, round(image_h * ratio))
                    installed = (False, (page_w - w) // 2, (page_h - h) // 2, w, h)
                    turned_expected = fit_layout(image_w, image_h, page_w, page_h, dpi, dpi)
                    if abs(image_w / image_h - label_w / label_h) < 0.02:  # image has the label's proportions
                        self.assertEqual(turned_expected, installed, (label_w, label_h, dpi, image_w, image_h))


if __name__ == '__main__':
    unittest.main()
