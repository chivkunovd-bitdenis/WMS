"""WMS-652/517 required Redis integration must not skip for missing executable."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class RedisDependencyContract(unittest.TestCase):
    def test_actual_setup_installs_missing_binary_and_preserves_present_binary(self):
        raw = (ROOT/'.github/workflows/ci.yml').read_text()
        job = raw.split('\n  backend-shards:\n', 1)[1].split('\n  backend:\n', 1)[0]
        step = job.split('      - name: Ensure required Redis integration executable\n', 1)[1]
        body = step.split('        run: |\n', 1)[1].split('      - uses:', 1)[0]
        command = '\n'.join(line[10:] for line in body.splitlines())
        for present in [False, True]:
            with self.subTest(present=present), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                redis = root/'redis-server'
                if present:
                    redis.write_text('#!/bin/bash\nexit 0\n')
                    redis.chmod(0o755)
                sudo = root/'sudo'
                sudo.write_text('#!/bin/bash\necho "$*" >> "$PROBE_DIR/apt.log"\n'
                    'if [[ "$*" == *install* ]]; then\n'
                    'printf "#!/bin/bash\\nexit 0\\n" > "$PROBE_DIR/redis-server"\n'
                    '/bin/chmod +x "$PROBE_DIR/redis-server"\nfi\n')
                sudo.chmod(0o755)
                result = subprocess.run(['/bin/bash', '-e', '-c', command], check=False,
                    capture_output=True, text=True, env={'PATH': folder, 'PROBE_DIR': folder})
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertTrue(redis.exists())
                if present:
                    self.assertFalse((root/'apt.log').exists())
                else:
                    self.assertIn('install -y redis-server', (root/'apt.log').read_text())


if __name__ == '__main__':
    unittest.main()
