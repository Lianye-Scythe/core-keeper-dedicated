#!/usr/bin/python3
import json
import fcntl
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'ops/diagnostics/network-evidence.py'))


class NetworkEvidenceTest(unittest.TestCase):
    def test_cm_endpoint(self):
        parse = module['cm_endpoint']
        self.assertEqual(parse('ConnectionCompleted() (205.196.6.132:443, WebSocket)'), ('205.196.6.132', 443))
        self.assertIsNone(parse('ConnectionCompleted() (999.1.1.1:443, WebSocket)'))
        self.assertIsNone(parse('ConnectionCompleted() (1.1.1.1:99999, WebSocket)'))
        self.assertIsNone(parse(''))

    def test_reader_primes_then_reads_and_handles_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'log'
            path.write_text('old timeout\n')
            reader = module['Reader']()
            self.assertEqual(reader.read(path), '')
            with path.open('a') as f:
                f.write('new timeout\n')
            self.assertEqual(reader.read(path), 'new timeout\n')
            path.write_text('short\n')
            self.assertEqual(reader.read(path), 'short\n')

    def test_normal_quit_is_not_incident(self):
        pattern = module['PATTERN']
        self.assertIsNone(pattern.search('Disconnected with reason App_Min'))
        self.assertIsNotNone(pattern.search('Disconnected with reason Remote_Timeout'))
        self.assertIsNotNone(pattern.search("ConnectionDisconnected('I/O Operation Failed')"))

    def test_failed_probes_need_multiple_endpoints(self):
        failed = module['network_failed']
        self.assertFalse(failed({'google': {'ok': False}}))
        self.assertFalse(failed({'steam-cm-tcp': {'ok': None}}))
        self.assertTrue(failed({'google': {'ok': False}, 'cloudflare': {'ok': False}}))
        self.assertTrue(failed({'steam-host': {'ok': False}, 'steam-container': {'ok': False}}))

    def test_rotation_and_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            append = module['append_sample']
            with patch.dict(append.__globals__, {'LOG_CAP': 48}):
                append(base, {'sample': 'A' * 30})
                append(base, {'sample': 'B' * 30})
            self.assertTrue((base / 'samples.previous.jsonl').exists())
            self.assertEqual(json.loads((base / 'samples.jsonl').read_text())['sample'], 'B' * 30)
            for number in range(4):
                (base / ('incident-' + str(number))).mkdir()
            module['retain_incidents'](base)
            self.assertEqual(sorted(p.name for p in base.glob('incident-*')), ['incident-2', 'incident-3'])

    def test_incident_window_and_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder = module['Recorder']()
            observe = recorder.observe
            with patch.dict(observe.__globals__, {'BASE': Path(temp)}), patch.object(recorder, 'snapshot'), \
                    patch('time.monotonic', side_effect=[100, 161, 170]):
                sample = {'utc': 'test', 'probes': {}}
                recorder.observe(sample, [{'source': 'test', 'line': 'Remote_Timeout'}], {})
                path = recorder.active
                self.assertIsNotNone(path)
                recorder.observe(sample, [], {})
                self.assertIsNone(recorder.active)
                self.assertTrue((path / 'complete.json').exists())
                self.assertEqual(len((path / 'window.jsonl').read_text().splitlines()), 2)
                recorder.observe(sample, [{'source': 'test', 'line': 'Remote_Timeout'}], {})
                self.assertIsNone(recorder.active)  # Cooldown prevents incident spam.

    def test_maintenance_lock_is_observed_without_disrupting_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'lock'
            path.touch()
            active = module['maintenance_active']
            self.assertFalse(active(path))
            with path.open('w') as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(active(path))
            self.assertFalse(active(path))


if __name__ == '__main__':
    unittest.main()
