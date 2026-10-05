"""CI build routing must skip only known documentation, not runtime inputs."""
import importlib.util
import os
from pathlib import Path
import subprocess
import textwrap
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'image_changes', Path(__file__).resolve().parents[1] / '.github/scripts/image-changes.py')
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


class ImageChangesTests(unittest.TestCase):
    def decision(self, paths):
        output = b'\0'.join(path.encode() for path in paths) + b'\0'
        with patch.object(changes.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output)) as run:
            result = changes.needs_image('pull_request', 'abc', 'def')
            self.assertIn('--no-renames', run.call_args.args[0])
            return result

    def test_known_documentation_skips(self):
        self.assertFalse(self.decision(['README.md', 'docs/README.zh-TW.md',
                                        'fex/README.md', 'fex/RESULTS.md',
                                        'ops/diagnostics/README.md', 'LICENSE']))

    def test_runtime_tests_workflows_and_unknown_paths_build(self):
        for path in ('Dockerfile', '.dockerignore', 'scripts/entry.sh',
                     'scripts/runtime.md', 'fex/install-rootfs.sh', 'fex/update.py',
                     'tests/test_updates.py', 'ops/diagnostics/core.py',
                     'docker-compose-example/core.env.example',
                     '.github/workflows/docker-image.yml', '.github/scripts/image-changes.py',
                     'new-file'):
            with self.subTest(path=path):
                self.assertTrue(self.decision(['README.md', path]))

    def test_scheduled_manual_and_missing_history_build(self):
        for event, base, head in (('schedule', 'abc', 'def'),
                                 ('workflow_dispatch', 'abc', 'def'),
                                 ('push', '0' * 40, 'def'),
                                 ('pull_request', None, 'def')):
            self.assertTrue(changes.needs_image(event, base, head))

    def test_diff_failure_builds(self):
        with patch.object(changes.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'git')):
            self.assertTrue(changes.needs_image('push', 'abc', 'def'))

    def test_push_uses_same_documentation_policy(self):
        with patch.object(changes.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'docs/configuration.md\0')):
            self.assertFalse(changes.needs_image('push', 'abc', 'def'))

    def test_required_gate_rejects_failed_cancelled_or_unexpected_skips(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    '.github/workflows/docker-image.yml').read_text()
        script = textwrap.dedent(workflow.split('  fex:\n', 1)[1].split('        run: |\n', 1)[1])
        base = dict(os.environ, CHANGES_RESULT='success', LINT_RESULT='success',
                    IMAGE_REQUIRED='true', RELEASES_RESULT='success', IMAGE_RESULT='success')
        scenarios = [({}, True),
                     ({'IMAGE_REQUIRED': 'false', 'RELEASES_RESULT': 'skipped', 'IMAGE_RESULT': 'skipped'}, True),
                     ({'LINT_RESULT': 'failure'}, False),
                     ({'CHANGES_RESULT': 'failure'}, False),
                     ({'IMAGE_RESULT': 'failure'}, False),
                     ({'IMAGE_RESULT': 'cancelled'}, False),
                     ({'IMAGE_RESULT': 'skipped'}, False),
                     ({'RELEASES_RESULT': 'failure'}, False),
                     ({'IMAGE_REQUIRED': ''}, False),
                     ({'IMAGE_REQUIRED': 'false'}, False)]
        for overrides, expected in scenarios:
            with self.subTest(overrides=overrides):
                result = subprocess.run(['bash', '-e', '-c', script], env={**base, **overrides},
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode == 0, expected)
