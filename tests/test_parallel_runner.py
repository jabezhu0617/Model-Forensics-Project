import contextlib
import io
import json
import tempfile
import threading
import unittest

from forensics import workflow
from forensics.demo import FixtureClient, FixtureSandbox
from forensics.prompts import digest
from forensics.runner import run_batch
from forensics.storage import Study


class ParallelBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.study = Study.create(self.temp.name)
        workflow.plan(self.study, {'id': 'base', 'kind': 'baseline', 'model': 'r1',
                                  'count': 8, 'synthetic': True})
        workflow.approve(self.study, 'base', 'test')

    def tearDown(self):
        self.temp.cleanup()

    def run_batch(self, factory, **kwargs):
        with self.study.lock(), contextlib.redirect_stdout(io.StringIO()):
            return run_batch(self.study, 'base', sandbox_factory=FixtureSandbox,
                             client_factory=factory, **kwargs)

    def test_parallel_clients_overlap_and_records_stay_separate(self):
        barrier = threading.Barrier(4, timeout=10)
        clients = []
        callback_threads = []
        coordinator = threading.get_ident()

        class IsolatedClient(FixtureClient):
            def __init__(self, run_id):
                super().__init__([True])
                self.run_id = run_id

            def complete(self, messages, tools=None):
                if len(messages) == 2:
                    barrier.wait()
                response = super().complete(messages, tools)
                response['choices'][0]['message']['content'] = self.run_id
                return response

        def factory(run_id):
            client = IsolatedClient(run_id)
            clients.append(client)
            return client

        result = self.run_batch(factory, workers=4,
            on_trial_finished=lambda run: callback_threads.append(threading.get_ident()))
        self.assertEqual(result['attempted'], 8)
        self.assertEqual(len({id(client) for client in clients}), 8)
        self.assertEqual(callback_threads, [coordinator] * 8)
        for run in self.study.runs('base'):
            self.assertEqual(run['status'], 'complete')
            self.assertEqual(run['transcript_hash'], digest(run['messages']))
            self.assertTrue(all(message['content'] == run['id'] for message in run['messages']
                                if message['role'] == 'assistant'))
            self.assertEqual(len(list((self.study.root / 'sealed' / run['id']).glob('step-*.json'))), 2)
        before = {path: path.read_bytes() for path in (self.study.root / 'runs').glob('*.json')}
        self.run_batch(lambda run_id: self.fail('Completed trials must not be rerun'), workers=4, retry_failed=True)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_failure_drains_active_trials_then_retry_preserves_attempt(self):
        barrier = threading.Barrier(2, timeout=10)
        failure_observed = threading.Event()

        class FailureClient(FixtureClient):
            def __init__(self, run_id):
                super().__init__([False])
                self.run_id = run_id

            def complete(self, messages, tools=None):
                if len(messages) == 2:
                    barrier.wait()
                    if self.run_id.endswith('0001'):
                        raise RuntimeError('Synthetic transport failure')
                    if not failure_observed.wait(10):
                        raise RuntimeError('Coordinator did not observe failure')
                return super().complete(messages, tools)

        result = self.run_batch(FailureClient, workers=2,
            on_trial_finished=lambda run: failure_observed.set() if run['status'] == 'failed' else None)
        self.assertEqual(result['attempted'], 2)
        self.assertEqual([run['status'] for run in self.study.runs('base')], ['failed', 'complete'])
        original = self.study.path('runs', 'base-0001').read_bytes()
        completed = self.study.path('runs', 'base-0002').read_bytes()
        result = self.run_batch(lambda run_id: FixtureClient([True]), workers=4, retry_failed=True)
        self.assertEqual(result['total_attempts_including_retries'], 9)
        self.assertEqual(self.study.path('runs', 'base-0001').read_bytes(), original)
        self.assertEqual(self.study.path('runs', 'base-0002').read_bytes(), completed)
        self.assertEqual(self.study.get('runs', 'base-0001-retry2')['attempt'], 2)
        self.assertTrue(all(run['status'] == 'complete' for run in self.study.runs('base')))
        audit = [json.loads(line) for line in (self.study.root / 'audit.jsonl').read_text().splitlines()]
        self.assertEqual(sum(item['action'] == 'retry' for item in audit), 1)

    def test_parallel_shared_client_and_invalid_worker_counts_rejected(self):
        for workers in (0, 17, True):
            with self.assertRaises(ValueError):
                self.run_batch(lambda run_id: FixtureClient([True]), workers=workers)
        with self.assertRaises(ValueError):
            run_batch(self.study, 'base', client=FixtureClient([True]), workers=2)
