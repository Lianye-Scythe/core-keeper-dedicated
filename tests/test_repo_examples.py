"""Check public docs and synthetic Compose config; never read private core.env."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_relative_markdown_links_exist(self):
        documents = [ROOT / 'README.md', *ROOT.glob('fex/*.md'),
                     *ROOT.glob('docs/*.md'), *ROOT.glob('ops/diagnostics/*.md')]
        for document in documents:
            for target in re.findall(r'\]\(([^\s)]+)\)', document.read_text()):
                if '://' in target:
                    continue
                with self.subTest(document=document.name, target=target):
                    path, _, anchor = target.partition('#')
                    destination = document.parent / path if path else document
                    self.assertTrue(destination.is_file())
                    if anchor:
                        headings = re.findall(r'^#{1,6} (.+)$', destination.read_text(), re.MULTILINE)
                        slugs = [re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
                                 for heading in headings]
                        self.assertIn(anchor, slugs)

    def test_diagnostics_python_syntax(self):
        for path in (ROOT / 'ops/diagnostics').glob('*.py'):
            with self.subTest(path=path.name):
                compile(path.read_text(), str(path), 'exec')


@unittest.skipUnless(shutil.which('docker'), 'Docker CLI required for Compose validation')
class ComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(['docker', 'compose', 'version'], capture_output=True, timeout=15)
        if result.returncode:
            raise unittest.SkipTest('Compose plugin unavailable')

    def render(self, environment=None):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'docker-compose.yml').write_text(
                (ROOT / 'docker-compose-example/docker-compose.yml').read_text())
            if environment is not None:
                (base / 'core.env').write_text(environment)
            result = subprocess.run(
                ['docker', 'compose', '-f', str(base / 'docker-compose.yml'), 'config', '--format', 'json'],
                capture_output=True, text=True, timeout=20, check=True)
            return json.loads(result.stdout)['services']['core-keeper']

    def test_no_env_file_uses_startup_updates(self):
        service = self.render()
        self.assertNotIn('UPDATE_GATE_ENABLED', service['environment'])
        self.assertEqual(service['logging']['options']['max-file'], '3')
        self.assertEqual(len(service['volumes']), 5)

    def test_quick_start_storage_matches_example(self):
        service = self.render()
        self.assertEqual({volume['source'] for volume in service['volumes']},
                         {f'/srv/corekeeper/{name}' for name in
                          ('server-data', 'server-files', 'fex-cache', 'mesa-cache', 'update-control')})

    def test_sample_environment_startup_updates(self):
        service = self.render((ROOT / 'docker-compose-example/core.env.example').read_text())
        self.assertEqual(service['environment']['UPDATE_GATE_ENABLED'], 'false')
        self.assertEqual(service['environment']['PUID'], '1000')

    def test_host_gate_can_be_enabled_in_environment_file(self):
        service = self.render('UPDATE_GATE_ENABLED=true\nGAME_ID=SyntheticGameId123\n')
        self.assertEqual(service['environment']['UPDATE_GATE_ENABLED'], 'true')
        self.assertEqual(service['environment']['GAME_ID'], 'SyntheticGameId123')


if __name__ == '__main__':
    unittest.main()
