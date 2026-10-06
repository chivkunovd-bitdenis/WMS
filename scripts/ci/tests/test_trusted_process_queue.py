"""WMS-652: bounded GitHub queue contract, not a live Actions scheduler test.

Documented queue semantics (checked 2026-10-06):
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency
The earlier two-thread mutex probe cannot model pending-run replacement.
"""
import re
import unittest

from scripts.ci.tests.test_trusted_process_publish import WORKFLOW


def configuration():
    section = WORKFLOW.read_text().split('concurrency:\n', 1)[1].split('\njobs:', 1)[0]
    fields = dict(re.findall(r'^  ([\w-]+): ([^\n]+)$', section, re.MULTILINE))
    return fields


class PendingQueue:
    """Single running publisher; max retains 100 pending, not an unbounded lock."""

    def __init__(self, mode):
        if mode not in {'single', 'max'}:
            raise AssertionError('Unsupported queue mode')
        self.mode = mode
        self.pending = []
        self.cancelled = []

    def submit(self, publication):
        if self.mode == 'single':
            self.cancelled.extend(self.pending)
            self.pending.clear()
        elif len(self.pending) == 100:
            self.cancelled.append(publication)
            return
        self.pending.append(publication)

    def finish_running_and_drain(self, running):
        # FIFO by waiting order in this scenario, not dispatch-time ordering.
        return [running, *self.pending]


def three_events(mode):
    queue = PendingQueue(mode)
    queue.submit(('A-new', 'head-A', 'failure'))
    queue.submit(('B-unrelated', 'head-B', 'success'))
    publications = queue.finish_running_and_drain(('A-old', 'head-A', 'success'))
    latest = {head: conclusion for _, head, conclusion in publications}
    return queue, publications, latest


class BoundedPublisherQueueTests(unittest.TestCase):
    def test_declared_global_queue_retains_pending_and_never_cancels_running(self):
        config = configuration()
        self.assertEqual(config['group'], 'process-integrity-publishers')
        self.assertEqual(config['cancel-in-progress'], 'false')
        self.assertEqual(config.get('queue', 'single'), 'max')

    def test_unrelated_third_event_cannot_replace_pending_failure_for_running_pr(self):
        # Negative control demonstrates the exact default-queue failure.
        single, _, old_latest = three_events('single')
        self.assertEqual(single.cancelled, [('A-new', 'head-A', 'failure')])
        self.assertEqual(old_latest['head-A'], 'success')
        queue, publications, latest = three_events(configuration().get('queue', 'single'))
        self.assertEqual(queue.cancelled, [])
        self.assertEqual(publications, [('A-old', 'head-A', 'success'),
            ('A-new', 'head-A', 'failure'), ('B-unrelated', 'head-B', 'success')])
        self.assertEqual(latest['head-A'], 'failure')

    def test_max_has_100_pending_limit_and_cancels_overflow_not_earlier_failure(self):
        queue = PendingQueue(configuration().get('queue', 'single'))
        failure = ('A-new', 'head-A', 'failure')
        queue.submit(failure)
        for index in range(99):
            queue.submit((f'B-{index}', f'head-B-{index}', 'success'))
        overflow = ('overflow', 'head-overflow', 'failure')
        queue.submit(overflow)
        self.assertEqual(len(queue.pending), 100)
        self.assertEqual(queue.pending[0], failure)
        self.assertEqual(queue.cancelled, [overflow])


if __name__ == '__main__':
    unittest.main()
