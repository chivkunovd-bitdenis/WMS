import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from wms_print_direct import Handler, Printer, default_printer, main

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

if __name__ == '__main__':
    unittest.main()
