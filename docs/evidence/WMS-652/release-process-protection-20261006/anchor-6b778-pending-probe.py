"""Bounded scheduler model, not a live GitHub test or production mutation.

GitHub's documented default single pending slot differs from threading.Lock.
Source: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency
"""
import json
import re
import subprocess

SHA = '6b778ebb2aa4b8dbb4580201841f5ba0bfc4430f'
raw = subprocess.check_output(['git', '-C', '/Users/deniscivkunov/Projects/WMS', 'show',
    SHA+':docs/evidence/WMS-652/trusted-anchor-20261006/process-integrity.yml'], text=True)
section = raw.split('concurrency:\n', 1)[1].split('\njobs:', 1)[0]
assert 'group: process-integrity-publishers' in section
assert 'cancel-in-progress: false' in section
match = re.search(r'^  queue: (\w+)$', section, re.MULTILINE)
mode = match.group(1) if match else 'single'

def simulate(mode):
    # A-old has already verified success and is finishing its POST.
    pending, cancelled, publications = [], [], []
    for event in [('A-new', 'A', 'failure'), ('B-unrelated', 'B', 'success')]:
        if mode == 'single' and pending:
            cancelled += [item[0] for item in pending]
            pending.clear()
        pending.append(event)
    publications.append(('A-old', 'A', 'success'))
    publications += pending
    latest = {head: conclusion for _, head, conclusion in publications}
    return dict(mode=mode, cancelled=cancelled, publications=publications, latest=latest)

actual = simulate(mode)
print('FROZEN_SHA', SHA)
print('DECLARED_QUEUE_MODEL', json.dumps(actual))
assert actual['cancelled'] == ['A-new'] and actual['latest']['A'] == 'success'
control = simulate('max')
print('IN_MEMORY_MAX_CONTROL', json.dumps(control))
assert control['cancelled'] == [] and control['latest']['A'] == 'failure'
print('Reproduced under documented scheduler semantics; no live check publication.')
