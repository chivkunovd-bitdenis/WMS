import base64
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from wms_print_direct import DefaultWindowsAdapter, Handler, Printer, default_printer, main

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

    def test_invalid_content_never_reaches_printer(self):
        with tempfile.TemporaryDirectory() as root:
            submit = Mock()
            with self.assertRaises(ValueError):
                Printer(Path(root), submit).print(job(data=b'not a png'))
            submit.assert_not_called()

    @patch('wms_print_direct.sys.argv', ['WMS Print'])
    @patch('wms_print_direct.subprocess.Popen')
    @patch('wms_print_direct.subprocess.run')
    @patch('wms_print_direct.Printer')
    @patch('wms_print_direct.ThreadingHTTPServer')
    def test_start_and_reopen_never_launch_browser(self, server, printer, run, popen):
        main()
        server.return_value.serve_forever.assert_called_once()
        server.side_effect = OSError('already running')
        main()
        run.assert_not_called()
        popen.assert_not_called()

    @patch('wms_print_direct.sys.platform', 'darwin')
    @patch('wms_print_direct.subprocess.run')
    def test_macos_default_uses_stable_locale(self, run):
        run.return_value.stdout = 'system default destination: Label_Printer\n'
        self.assertEqual(default_printer(), 'Label_Printer')
        self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')

    def test_windows_health_and_print_resolve_the_system_default_printer(self):
        win32print = SimpleNamespace(GetDefaultPrinter=Mock(return_value='Xprinter XP-420B'))
        with (
            patch('wms_print_direct.sys.platform', 'win32'),
            patch.dict(sys.modules, {'win32print': win32print}),
        ):
            self.assertEqual(default_printer(), 'Xprinter XP-420B')
        win32print.GetDefaultPrinter.assert_called_once_with()

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

        class FakeImage:
            width = 464
            height = 320

            def convert(self, mode):
                self.mode = mode
                return self

        class FakeDib:
            def __init__(self, image):
                self.image = image

            def draw(self, handle, target):
                calls.append(('draw', handle, target))

        adapter = DefaultWindowsAdapter({
            'win32print': FakePrint,
            'win32gui': SimpleNamespace(CreateDC=lambda driver, queue, devmode: 17),
            'win32ui': SimpleNamespace(CreateDCFromHandle=lambda handle: FakeDc()),
            'Image': SimpleNamespace(open=lambda stream: FakeImage()),
            'ImageWin': SimpleNamespace(Dib=FakeDib),
            'fitz': None,
        })

        self.assertEqual(
            adapter.submit_default(PNG, 'Xprinter XP-420B', 58, 40),
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

if __name__ == '__main__':
    unittest.main()
