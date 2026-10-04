"""Offline transaction tests: never contact Docker, Steam or production saves."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from fex import readiness, update


def deployment(base):
    env = ['COREKEEPER_RUNTIME=fex', 'USE_DEPOT_DOWNLOADER=true', 'PUID=1001',
           'PGID=1001', 'WORLD_INDEX=0', 'WORLD_NAME=Keep This World',
           'GAME_ID=KeepThisGameId123', 'FEX_MAXINST=16', 'FEX_MULTIBLOCK=1',
           'FEX_SMCCHECKS=1', 'ACTIVATE_ALL_CONTENT=true', 'UPDATE_GATE_ENABLED=true']
    mounts = [("server-data", "/home/steam/core-keeper-data"),
              ("server-files", "/home/steam/core-keeper-dedicated"),
              ("fex-cache", "/home/steam/.cache/fex"),
              ("mesa-cache", "/home/steam/.cache/mesa_shader_cache"),
              ("update-control", "/run/corekeeper-update")]
    return dict(Name='/core-keeper-dedicated', Image='old-image',
                State=dict(Running=True, StartedAt='one'),
                Config=dict(Env=env, Entrypoint=['/usr/bin/tini', '--'],
                            Cmd=['bash', 'scripts/entry.sh'], StopTimeout=120, User=''),
                HostConfig=dict(NetworkMode='bridge', RestartPolicy=dict(Name='unless-stopped'),
                                Memory=10 * 1024**3, MemorySwap=10 * 1024**3,
                                Ulimits=[dict(Name='core', Soft=-1, Hard=-1)]),
                Mounts=[dict(Type='bind', Source=str(base / source), Destination=target, RW=True)
                        for source, target in mounts])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        for directory in ('server-data', 'server-files', 'fex-cache', 'mesa-cache',
                          'backups', 'update-control', 'update-state', 'ops'):
            (self.base / directory).mkdir()
        (self.base / 'server-data/world').write_text('original world')
        (self.base / 'server-files/game').write_text('old game')
        (self.base / 'server-files/.corekeeper-buildid').write_text('100\n')
        self.info = deployment(self.base)
        self.config = dict(base=str(self.base), container='core-keeper-dedicated',
                           image='image:fex', required_mountpoint='/',
                           readiness_helper='/fake/helper', backup_keep=2,
                           maintenance_hour=(dt.datetime.now(dt.timezone.utc).hour + 1) % 24,
                           timezone='UTC', readiness_timeout=1)
        self.commands = []
        self.candidate_exists = False
        self.fault = None

    def fake_run(self, args, timeout=120, check=True):
        self.commands.append(args)
        if args[0] == 'tar':
            return subprocess.run(args, capture_output=True, text=True, check=check)
        if args[:3] == ['docker', 'image', 'inspect']:
            image = args[3]
            info = dict(Id='new-image' if image == 'image:fex' else image,
                        Config=dict(Env=self.info['Config']['Env']),
                        RepoDigests=['image@sha256:123'])
            return subprocess.CompletedProcess(args, 0, json.dumps([info]), '')
        if args[:2] == ['docker', 'create']:
            if self.fault == 'create':
                raise subprocess.CalledProcessError(1, args)
            self.candidate_exists = True
        if args[:2] == ['docker', 'inspect']:
            return subprocess.CompletedProcess(args, 0 if self.candidate_exists else 1, '', '')
        if args[:2] == ['docker', 'start'] and self.candidate_exists:
            (self.base / 'server-data/world').write_text('candidate world')
            (self.base / 'server-files/game').write_text('new game')
            if self.fault != 'marker':
                (self.base / 'server-files/.corekeeper-buildid').write_text('101\n')
        if args[:3] == ['docker', 'rm', '-f']:
            self.candidate_exists = False
        return subprocess.CompletedProcess(args, 0, '', '')

    def perform(self, force=False, latest='101', fingerprints=None, ready=None):
        fingerprint = fingerprints or (lambda image: image)
        with patch.object(update, 'run', side_effect=self.fake_run), \
                patch.object(update, 'inspect_container', return_value=self.info), \
                patch.object(update, 'latest_build', return_value=latest), \
                patch.object(update, 'image_fingerprint', side_effect=fingerprint), \
                patch.object(update, 'wait_ready', side_effect=ready or [True]), \
                patch.object(update.os, 'chown'), patch.object(update.os, 'access', return_value=True):
            update.maintain(self.config, force)

    def test_check_queues_without_stopping(self):
        self.perform()
        self.assertTrue((self.base / 'update-state/pending.json').exists())
        self.assertFalse(any(command[:2] == ['docker', 'stop'] for command in self.commands))

    def test_identical_contents_do_not_restart(self):
        self.perform(latest='100', fingerprints=lambda image: 'same')
        self.assertFalse((self.base / 'update-state/pending.json').exists())
        self.assertFalse(any(command[:2] == ['docker', 'stop'] for command in self.commands))

    def test_success_records_verified_build(self):
        self.perform(force=True)
        state = json.loads((self.base / 'update-state/installed.json').read_text())
        self.assertEqual(state['game_build'], '101')
        self.assertFalse((self.base / 'update-state/transaction.json').exists())
        archive, = (self.base / 'backups').glob('*.tar.gz')
        update.validate_archive(archive)
        with tarfile.open(archive) as saved:
            self.assertEqual(saved.extractfile('server-data/world').read(), b'original world')
            self.assertEqual(saved.extractfile('server-files/game').read(), b'old game')

    def test_create_failure_restores_original(self):
        self.fault = 'create'
        with self.assertRaises(subprocess.CalledProcessError):
            self.perform(force=True)
        self.assertEqual((self.base / 'server-data/world').read_text(), 'original world')
        self.assertEqual((self.base / 'server-files/game').read_text(), 'old game')
        self.assertFalse((self.base / 'update-state/transaction.json').exists())

    def test_startup_failure_restores_game_and_world(self):
        with self.assertRaisesRegex(RuntimeError, 'simulation-ready'):
            self.perform(force=True, ready=[False, True])
        self.assertEqual((self.base / 'server-data/world').read_text(), 'original world')
        self.assertEqual((self.base / 'server-files/game').read_text(), 'old game')
        self.assertEqual((self.base / 'server-files/.corekeeper-buildid').read_text().strip(), '100')

    def test_uncertified_build_rolls_back(self):
        self.fault = 'marker'
        with self.assertRaisesRegex(RuntimeError, 'uncertified'):
            self.perform(force=True, ready=[True, True])
        self.assertEqual((self.base / 'server-data/world').read_text(), 'original world')

    def test_rollback_failure_keeps_journal(self):
        with self.assertRaisesRegex(RuntimeError, 'Rollback did not'):
            self.perform(force=True, ready=[False, False])
        self.assertTrue((self.base / 'update-state/transaction.json').exists())

    def test_interrupted_transaction_blocks_new_maintenance(self):
        (self.base / 'update-state/transaction.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Unfinished transaction'):
            self.perform(force=True)
        self.assertFalse(self.commands)

    def test_stopped_server_not_started(self):
        self.info['State']['Running'] = False
        with self.assertRaisesRegex(ValueError, 'intentional stop'):
            self.perform(force=True)

    def test_unknown_build_is_queued_not_assumed_current(self):
        (self.base / 'server-files/.corekeeper-buildid').unlink()
        self.perform(latest='100', fingerprints=lambda image: 'same')
        self.assertTrue(json.loads((self.base / 'update-state/pending.json').read_text())['game_changed'])

    def test_preserve_world_and_limits(self):
        with patch.object(update, 'run', side_effect=self.fake_run):
            args = update.replacement_args(self.info, 'new-image', self.base)
        for setting in ('WORLD_INDEX=0', 'WORLD_NAME=Keep This World',
                        'GAME_ID=KeepThisGameId123', 'ACTIVATE_ALL_CONTENT=true', 'FEX_MAXINST=16'):
            self.assertIn(setting, args)
        self.assertEqual(args[args.index('--memory') + 1], str(10 * 1024**3))
        self.assertNotIn('--cpus', args)

    def test_unexpected_mount_rejected(self):
        self.info['Mounts'][0]['Source'] = '/other/world'
        with self.assertRaisesRegex(ValueError, 'Unexpected mount'):
            self.perform(force=True)
        self.assertFalse(any(command[:2] == ['docker', 'stop'] for command in self.commands))

    def test_custom_network_rejected(self):
        self.info['HostConfig']['NetworkMode'] = 'custom-network'
        with self.assertRaisesRegex(ValueError, 'default Docker bridge'):
            self.perform(force=True)

    def test_backup_failure_restarts_original_without_update(self):
        (self.base / 'server-data/link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'Unsafe rollback'):
            self.perform(force=True)
        self.assertFalse(any(command[:2] == ['docker', 'create'] for command in self.commands))
        self.assertFalse(list((self.base / 'backups').glob('*.tar.gz')))

    def test_retention_only_deletes_matching_backups(self):
        backups = self.base / 'backups'
        for name in ('corekeeper-full-1.tar.gz', 'corekeeper-full-2.tar.gz',
                     'corekeeper-full-3.tar.gz', 'other.tar.gz'):
            (backups / name).touch()
        update.prune_backups(backups, 2)
        self.assertEqual(sorted(path.name for path in backups.iterdir()),
                         ['corekeeper-full-2.tar.gz', 'corekeeper-full-3.tar.gz', 'other.tar.gz'])

    def test_missing_data_mount_fails_closed(self):
        with patch.object(update.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(ValueError, 'data mount'):
                update.validate_paths(self.base, '/not-mounted')

    def test_bad_archive_path_is_rejected(self):
        path = self.base / 'bad.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo('../outside')
            info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        with self.assertRaisesRegex(ValueError, 'Unsafe rollback'):
            update.validate_archive(path)


class ReadinessTests(unittest.TestCase):
    def test_new_world_ready(self):
        self.assertTrue(readiness.logs_ready('Started session with info:\nstarting a new world :\ntimescale = 0\n'))

    def test_loaded_world_ready(self):
        self.assertTrue(readiness.logs_ready('Started session with info:\nsuccessfully loaded world file into SerializeWorld\ntimescale = 1\n'))

    def test_gameid_alone_is_not_ready(self):
        self.assertFalse(readiness.logs_ready('Game ID: ABC\nStarted session with info:\n'))

    def test_timescale_before_world_is_not_ready(self):
        self.assertFalse(readiness.logs_ready('Started session with info:\ntimescale = 0\nstarting a new world :\n'))


if __name__ == '__main__':
    unittest.main()
