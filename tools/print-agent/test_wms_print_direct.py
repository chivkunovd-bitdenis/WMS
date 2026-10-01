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

def job(key='scan-1', data=PNG):
    return {'idempotencyKey': key, 'imageDataUrl': 'data:image/png;base64,' + base64.b64encode(data).decode()}


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

    def submit_default(self, data, queue, mark):
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
            def submit_default(self, data, queue, mark):
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
            adapter.submit_default = lambda data, queue, mark: (mark(), 'Label-2')[1]
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
            def submit_default(self, data, queue, mark):
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

                def submit_default(inner, data, queue, mark):
                    mark()
                    sent.append(1)
                    return 'Label-1'

            printer = self.printer(root, Locking())
            printer.print_timeout, printer.minimum_to_start = 1.2, 0.5
            with self.assertRaises(PrintNotSent) as raised:
                printer.print(job())
            self.assertIn('не отправлялось', str(raised.exception))
            self.assertEqual(sent, [])
            self.assertIsNone(printer._lookup('scan-1'))
            printer.print_timeout, printer.minimum_to_start = 5, 0.5
            self.assertEqual(printer.print(job()), 'Label-1')


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
        return {8: self.area[0], 10: self.area[1], 88: self.dpi[0], 90: self.dpi[1]}[index]

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
        adapter._create_printer_dc = Mock(side_effect=dc_error, return_value=dc)
        return adapter, drawn

    def test_undecodable_png_fails_before_mark(self):
        mark = Mock()
        adapter, _ = self.adapter(FakeDC())
        with self.assertRaises(Exception):
            adapter.submit_default(b'\x89PNG\r\n\x1a\ntest', 'Q', mark)
        mark.assert_not_called()

    def test_driver_failure_fails_before_mark(self):
        mark = Mock()
        adapter, _ = self.adapter(dc_error=ValueError('driver refused'))
        with self.assertRaises(ValueError):
            adapter.submit_default(png(), 'Q', mark)
        mark.assert_not_called()

    def test_mark_is_set_right_before_start_doc(self):
        events = []
        adapter, drawn = self.adapter(FakeDC(events=events))
        self.assertEqual(adapter.submit_default(png(size=(58, 40)), 'Q', lambda: events.append('mark')), 'windows-5')
        self.assertEqual(events[:2], ['mark', 'StartDoc'])
        self.assertEqual(drawn[0][1], (0, 0, 464, 320))  # unchanged landscape-on-landscape fit

    def test_landscape_label_on_portrait_page_is_turned_and_larger(self):
        adapter, drawn = self.adapter(FakeDC(area=(320, 464)))
        adapter.submit_default(png(size=(580, 400)), 'Q', lambda: None)
        size, box = drawn[0]
        self.assertEqual(size, (400, 580))  # turned by 90 degrees
        self.assertEqual(box, (0, 0, 320, 464))

    def test_failure_after_start_doc_is_unknown_outcome(self):
        dc = FakeDC()
        dc.EndPage = Mock(side_effect=OSError('spooler'))
        adapter, _ = self.adapter(dc)
        with self.assertRaises(agent.UnknownPrintOutcome):
            adapter.submit_default(png(), 'Q', lambda: None)
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


if __name__ == '__main__':
    unittest.main()
