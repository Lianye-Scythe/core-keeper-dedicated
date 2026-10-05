"""Synthetic host settings only: no real configuration, daemon or system writes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('host_settings', ROOT / 'ops/diagnostics/host_config.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


class HostSettingsTests(unittest.TestCase):
    def settings(self, **changes):
        return dict(base='/srv/corekeeper', required_mountpoint='/',
                    container='core-keeper-dedicated', **changes)

    def test_public_example_is_valid(self):
        config = json.loads((ROOT / 'examples/scheduled-updates/corekeeper-update-check.json.example').read_text())
        self.assertEqual(host.validate(config), config)
        self.assertEqual(config['required_mountpoint'], '/')
        self.assertEqual(config['timezone'], 'UTC')

    def test_dedicated_mount_at_base_is_valid(self):
        config = self.settings()
        config['required_mountpoint'] = config['base']
        host.validate(config)

    def test_unsafe_paths_and_names_rejected(self):
        for base in ('/', '/srv', '/srv/../etc', '/srv/with space', '/srv/%x', '/srv/a\nb'):
            config = self.settings()
            config['base'] = base
            with self.subTest(base=base), self.assertRaises(ValueError):
                host.validate(config)
        config = self.settings()
        config['container'] = '--privileged'
        with self.assertRaises(ValueError):
            host.validate(config)

    def test_wrong_mount_and_memory_rejected(self):
        config = self.settings()
        config['required_mountpoint'] = '/data'
        with self.assertRaises(ValueError):
            host.validate(config)
        for memory in ('0g', '10g --privileged', 10):
            with self.subTest(memory=memory), self.assertRaises(ValueError):
                host.validate(self.settings(memory_limit=memory))

    def test_permissions_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'config'
            path.write_text('{}')
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                host.private_file(path)
            link = Path(temp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                host.private_file(link)

    def test_custom_dropins_have_no_personal_paths(self):
        config = self.settings()
        config['base'] = '/mnt/game/corekeeper'
        config['required_mountpoint'] = '/mnt/game'
        text = '\n'.join(host.dropins(host.validate(config)).values())
        self.assertIn('ReadWritePaths=/mnt/game/corekeeper/diagnostics/network', text)
        self.assertNotIn('/data/corekeeper', text)
        self.assertIn('RequiresMountsFor=/mnt/game/corekeeper', text)

    def test_missing_mount_fails_closed(self):
        with patch.object(host.os.path, 'ismount', return_value=False):
            with self.assertRaises(RuntimeError):
                host.check_storage(self.settings())

    def test_storage_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'game'
            base.mkdir()
            (base / 'diagnostics').symlink_to(Path(temp), target_is_directory=True)
            config = self.settings()
            config['base'] = str(base)
            with patch.object(host.os.path, 'ismount', return_value=True):
                with self.assertRaises(RuntimeError):
                    host.check_storage(config)

    def test_container_mount_mismatch_is_rejected(self):
        info = [{'Mounts': [{'Type': 'bind', 'Destination': '/home/steam/core-keeper-data',
                            'Source': '/other/saves'}]}]
        with patch.object(host.subprocess, 'check_output', return_value=json.dumps(info).encode()):
            with self.assertRaises(ValueError):
                host.check_container(self.settings())

    def test_bootstrap_preserves_game_env_without_forcing_personal_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'game'
            base.mkdir()
            for name in ('server-data', 'server-files', 'fex-cache', 'mesa-cache', 'update-control', 'ops'):
                (base / name).mkdir()
            (base / 'ops/fex-image-ref').write_text('example/image@sha256:' + 'a' * 64)
            config = self.settings(memory_limit='10g')
            config['base'] = str(base)
            info = [{'Architecture': 'arm64', 'Config': {'Env': ['COREKEEPER_RUNTIME=fex']}}]
            with patch.object(host, 'check_storage'), patch.object(host, 'private_file'), \
                    patch.object(host.subprocess, 'check_output', return_value=json.dumps(info).encode()), \
                    patch.object(host.subprocess, 'run', side_effect=[Mock(returncode=1), Mock(returncode=0)]) as run:
                host.bootstrap(config)
            args = run.call_args.args[0]
            self.assertIn('--env-file', args)
            self.assertNotIn('-e', args)
            self.assertNotIn('--ulimit', args)
            self.assertIn('--memory', args)
            self.assertEqual(args.count('--mount'), 5)

    def test_existing_container_is_never_replaced(self):
        config = self.settings()
        with patch.object(host, 'check_storage'), patch.object(host, 'private_file'), \
                patch.object(host.Path, 'read_text', return_value='image@sha256:' + 'a' * 64), \
                patch.object(host.subprocess, 'check_output', return_value=b'[{"Architecture":"arm64","Config":{"Env":["COREKEEPER_RUNTIME=fex"]}}]'), \
                patch.object(host.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            with self.assertRaises(ValueError):
                host.bootstrap(config)
            self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
