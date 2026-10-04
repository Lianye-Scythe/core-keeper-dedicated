import importlib.util
from pathlib import Path
import os
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('retention', Path(__file__).resolve().parents[1] / 'ops/diagnostics/retention.py')
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 10000000

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, modified=1):
        path = self.root / name
        path.write_bytes(b'log line\n' * 1024)
        os.utime(path, (modified, modified))
        return path

    def test_age_and_newest_two(self):
        paths = [self.file(str(i), i + 1) for i in range(4)]
        retention.prune(paths, set(), 100, 1024**3, self.now)
        self.assertEqual([p.exists() for p in paths], [False, False, True, True])

    def test_open_child_preserves_directory(self):
        old = self.root / 'old'
        old.mkdir()
        child = old / 'open.log'
        child.write_text('open')
        os.utime(child, (1, 1))
        os.utime(old, (1, 1))
        newer = [self.file('new1', 20), self.file('new2', 30)]
        retention.prune([old, *newer], {child}, 100, 1, self.now)
        self.assertTrue(child.exists())

    def test_recent_preserved(self):
        paths = [self.file(str(i), self.now - i * 10) for i in range(4)]
        retention.prune(paths, set(), 1, 1, self.now)
        self.assertTrue(all(p.exists() for p in paths))

    def test_symlinks_excluded(self):
        target = self.file('target')
        link = self.root / 'link'
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            retention.measure(link)
        self.assertTrue(target.exists())

    def test_dry_run_no_deletion(self):
        paths = [self.file(str(i), i + 1) for i in range(4)]
        retention.prune(paths, set(), 100, 1, self.now, dry=True)
        self.assertTrue(all(p.exists() for p in paths))

    def test_budget_removes_oldest(self):
        paths = [self.file(str(i), i + 1) for i in range(4)]
        budget = sum(retention.measure(p)[0] for p in paths[1:])
        retention.prune(paths, set(), self.now * 2, budget, self.now)
        self.assertEqual([p.exists() for p in paths], [False, True, True, True])

    def test_compression_keeps_open_log(self):
        path = self.file('current.log')
        retention.compress_closed_logs([path], {path}, self.now)
        self.assertTrue(path.exists())
        self.assertFalse(path.with_suffix('.log.gz').exists())

    def test_compression_ignores_special_files(self):
        path = self.root / 'pipe.log'
        os.mkfifo(path)
        os.utime(path, (1, 1))
        retention.compress_closed_logs([path], set(), self.now)
        self.assertTrue(path.exists())
        self.assertFalse(path.with_suffix('.log.gz').exists())

    @unittest.skipUnless(os.geteuid() == 0, 'Ownership restoration requires root')
    def test_compression_round_trip(self):
        path = self.file('old.log')
        content = path.read_bytes()
        retention.compress_closed_logs([path], set(), self.now)
        self.assertFalse(path.exists())
        with retention.gzip.open(path.with_suffix('.log.gz'), 'rb') as source:
            self.assertEqual(source.read(), content)


if __name__ == '__main__':
    unittest.main()
