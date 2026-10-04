import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'ops/diagnostics'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load('core_config', 'core-config.py')
crash = load('crash_evidence', 'crash-evidence.py')


class CoreConfigTests(unittest.TestCase):
    def test_apport_preserved(self):
        pattern = '|/usr/share/apport/apport -p%p -s%s -c%c -d%d -P%P -u%u -g%g -F%F -- %E'
        saved = config.make_config(pattern, '10')
        self.assertEqual(saved['original_core_pattern'], pattern)
        self.assertEqual(saved['original_core_pipe_limit'], 10)
        self.assertEqual(saved['apport_argv'][-2:], ['--', '%E'])

    def test_other_handler_rejected(self):
        for pattern in ('core', '|/usr/lib/systemd/systemd-coredump %P', config.ROUTED_PATTERN):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                config.make_config(pattern, 10)

    def test_unknown_placeholder_rejected(self):
        with self.assertRaises(ValueError):
            config.make_config('|/usr/share/apport/apport %h', 10)

    def test_zero_pipe_limit_rejected(self):
        with self.assertRaises(ValueError):
            config.make_config('|/usr/share/apport/apport %p', 0)


class CrashEvidenceTests(unittest.TestCase):
    def test_retain_two_without_following_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            outside = base / 'untouched'
            outside.mkdir()
            for index in range(4):
                path = base / f'crash-{index}'
                path.mkdir()
                crash.os.utime(path, (index + 1, index + 1))
            (base / 'crash-link').symlink_to(outside)
            with patch.object(crash, 'BASE', base):
                crash.retain()
            self.assertEqual(sorted(p.name for p in base.glob('crash-*') if not p.is_symlink()),
                             ['crash-2', 'crash-3'])
            self.assertTrue(outside.is_dir())
            self.assertTrue((base / 'crash-link').is_symlink())

    def test_target_failure_is_not_claimed_as_game(self):
        with patch.object(crash.os, 'stat', side_effect=FileNotFoundError):
            self.assertFalse(crash.is_target('123'))

    def test_invalid_kernel_arguments_rejected(self):
        with self.assertRaises(ValueError):
            crash.core(['123'])

    def test_private_metadata_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.json'
            crash.write(path, {'synthetic': True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
