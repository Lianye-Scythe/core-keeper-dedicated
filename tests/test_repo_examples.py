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
    def test_bilingual_readme_shell_commands_match(self):
        snippets = []
        for path in (ROOT / 'README.md', ROOT / 'docs/README.zh-TW.md'):
            snippets.append(re.findall(r'```sh\n(.*?)\n```', path.read_text(), re.DOTALL))
        self.assertTrue(snippets[0])
        self.assertEqual(snippets[0], snippets[1])

    def test_bilingual_readme_key_settings_and_guide_coverage(self):
        keys = ('PUID', 'PGID', 'WORLD_NAME', 'WORLD_INDEX', 'GAME_ID',
                'MAX_PLAYERS', 'ACTIVATE_ALL_CONTENT', 'UPDATE_GATE_ENABLED')
        defaults = dict(line.split('=', 1) for line in
                        (ROOT / 'docker-compose-example/core.env.example').read_text().splitlines()
                        if line and not line.startswith('#') and '=' in line)
        guides = [ROOT / 'docs' / f'{name}.md' for name in
                  ('deployment', 'configuration', 'maintenance', 'troubleshooting', 'migration')]
        guides += [ROOT / 'fex/README.md', ROOT / 'ops/diagnostics/README.md']
        for path in (ROOT / 'README.md', ROOT / 'docs/README.zh-TW.md'):
            text = path.read_text()
            with self.subTest(document=path.name):
                for key in keys:
                    row = next(line for line in text.splitlines()
                               if line.startswith('|') and f'`{key}`' in line)
                    if defaults[key]:
                        self.assertIn(f'`{defaults[key]}`', row)
                self.assertIn('2.24.0', text)
                self.assertIn('04:00 UTC', text)
                targets = {((path.parent / target.split('#')[0]).resolve())
                           for target in re.findall(r'\]\(([^\s)]+)\)', text)
                           if '://' not in target}
                self.assertTrue(set(guides).issubset(targets))

    def test_shell_examples_parse_without_executing(self):
        documents = [ROOT / 'README.md', *ROOT.glob('docs/*.md'),
                     *ROOT.glob('fex/*.md'), ROOT / 'ops/diagnostics/README.md']
        for document in documents:
            for number, snippet in enumerate(re.findall(r'```(?:sh|bash)\n(.*?)\n```',
                                                        document.read_text(), re.DOTALL)):
                with self.subTest(document=document.name, snippet=number):
                    result = subprocess.run(['bash', '-n'], input=snippet, text=True,
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_first_install_examples_never_overwrite_existing_config(self):
        for document in ('docs/maintenance.md', 'ops/diagnostics/README.md'):
            text = (ROOT / document).read_text()
            block, = re.findall(r'(if ! sudo test -e /etc/corekeeper-update-check.json .*?\nfi)',
                                text, re.DOTALL)
            with tempfile.TemporaryDirectory() as temp:
                config = Path(temp) / 'host.json'
                script = block.replace('sudo ', '').replace('/etc/corekeeper-update-check.json', str(config))
                def execute():
                    subprocess.run(['bash', '-e', '-c', script], cwd=ROOT,
                                   capture_output=True, text=True, check=True, timeout=10)
                execute()
                self.assertEqual(json.loads(config.read_text())['timezone'], 'UTC')
                config.write_text('{"timezone":"Asia/Taipei","maintenance_hour":17}')
                original = config.read_bytes()
                execute()
                self.assertEqual(config.read_bytes(), original)
                config.unlink()
                config.symlink_to(Path(temp) / 'missing')
                execute()
                self.assertTrue(config.is_symlink())
                self.assertFalse(config.exists())

    def test_migration_property_example_is_valid_json(self):
        text = (ROOT / 'docs/migration.md').read_text()
        snippet, = re.findall(r'```json\n(.*?)\n```', text, re.DOTALL)
        self.assertEqual(json.loads(snippet)['game_env_file'], '/etc/corekeeper-fex.env')

    def test_compose_minimum_version_is_explicit(self):
        for path in (ROOT / 'README.md', ROOT / 'docs/deployment.md'):
            self.assertIn('2.24.0', path.read_text())

    def test_join_id_commands_use_game_working_directory(self):
        for path in [ROOT / 'README.md', ROOT / 'docs/troubleshooting.md']:
            commands = re.findall(r'docker exec .*cat (\S+/GameID.txt)', path.read_text())
            self.assertTrue(commands)
            self.assertEqual(set(commands), {'/home/steam/core-keeper-dedicated/GameID.txt'})
        self.assertIn('cd "${STEAMAPPDIR}"', (ROOT / 'scripts/launch.sh').read_text())

    def test_obsolete_compose_env_removed(self):
        self.assertFalse((ROOT / 'docker-compose-example/.env').exists())

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
        self.assertEqual(service['environment']['ACTIVATE_ALL_CONTENT'], 'false')

    def test_content_activation_is_opt_in(self):
        service = self.render('ACTIVATE_ALL_CONTENT=true\n')
        self.assertEqual(service['environment']['ACTIVATE_ALL_CONTENT'], 'true')

    def test_host_gate_can_be_enabled_in_environment_file(self):
        service = self.render('UPDATE_GATE_ENABLED=true\nGAME_ID=SyntheticGameId123\n')
        self.assertEqual(service['environment']['UPDATE_GATE_ENABLED'], 'true')
        self.assertEqual(service['environment']['GAME_ID'], 'SyntheticGameId123')


if __name__ == '__main__':
    unittest.main()
