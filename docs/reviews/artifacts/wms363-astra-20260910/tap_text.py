"""Tap one exact visible text match, using a fresh emulator UI hierarchy."""
import re
import subprocess
import sys
from ui_dump import ADB, hierarchy

for label in sys.argv[1:]:
    nodes = []
    for _ in range(5):
        nodes = [n for n in hierarchy().iter('node') if n.get('text') == label]
        if len(nodes) == 1:
            break
    if len(nodes) != 1:
        raise SystemExit(f'Expected one visible match for {label}, found {len(nodes)}')
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', nodes[0].get('bounds')))
    subprocess.run([ADB, '-s', 'emulator-5554', 'shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2)], check=True)
