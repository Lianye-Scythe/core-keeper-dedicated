"""Shared, root-owned host settings for bootstrap, maintenance and diagnostics."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess

CONFIG = Path('/etc/corekeeper-update-check.json')
DEFAULT_BASE = Path('/srv/corekeeper')
DEFAULT_CONTAINER = 'core-keeper-dedicated'


def safe_path(value):
    if not isinstance(value, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]*', value):
        raise ValueError('Use an absolute host path without whitespace or shell/systemd escapes')
    path = Path(value)
    if '..' in path.parts or str(path) != value:
        raise ValueError('Use a normalized absolute path')
    return path


def validate(config):
    config = dict(config)
    base = safe_path(config['base'])
    mount = safe_path(config['required_mountpoint'])
    if len(base.parts) < 3 or mount not in (base, *base.parents):
        raise ValueError('Base must be a scoped directory on the required filesystem mount')
    name = config['container']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
        raise ValueError('Invalid container name')
    memory = config.get('memory_limit', '')
    if not isinstance(memory, str) or (memory and not re.fullmatch(r'[1-9][0-9]*[mMgG]', memory)):
        raise ValueError('memory_limit must be empty or a positive Docker size, e.g. 10g')
    if not isinstance(config.get('allow_core_dumps', False), bool):
        raise ValueError('allow_core_dumps must be boolean')
    for key in ('game_env_file', 'image_ref_file'):
        if key in config:
            safe_path(config[key])
    return config


def private_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError('Expected a root-owned private regular file: ' + str(path))


def load(path=CONFIG):
    path = Path(path)
    private_file(path)
    return validate(json.loads(path.read_text()))


def check_storage(config):
    base = Path(config['base'])
    mount = Path(config['required_mountpoint'])
    if not os.path.ismount(mount):
        raise RuntimeError('Required filesystem is not mounted: ' + str(mount))
    for path in (base, *base.parents):
        if path.is_symlink():
            raise RuntimeError('Symlink in host base path: ' + str(path))
    if not base.is_dir():
        raise RuntimeError('Missing host base directory: ' + str(base))
    for relative in ('server-data', 'server-files', 'server-files/logs',
                     'fex-cache', 'mesa-cache', 'update-control', 'diagnostics',
                     'diagnostics/network', 'runtime-test'):
        if (base / relative).is_symlink():
            raise RuntimeError('Symlink in managed storage: ' + str(base / relative))


def check_container(config):
    info = json.loads(subprocess.check_output(['docker', 'container', 'inspect', config['container']]))[0]
    mounts = {item['Destination']: item['Source'] for item in info['Mounts'] if item['Type'] == 'bind'}
    for directory, target in [('server-data', '/home/steam/core-keeper-data'),
                              ('server-files', '/home/steam/core-keeper-dedicated')]:
        if mounts.get(target) != str(Path(config['base']) / directory):
            raise ValueError('Container mounts do not match the configured host base')


def dropins(config):
    base = config['base']
    common = '[Unit]\nRequiresMountsFor=\nRequiresMountsFor=' + base + '\n'
    return {
        'corekeeper-crash-evidence.service': common,
        'corekeeper-network-evidence.service': common +
            '[Service]\nReadWritePaths=\nReadWritePaths=' + base + '/diagnostics/network\n',
        'corekeeper-diagnostics-retention.service': common +
            '[Service]\nReadWritePaths=\nReadWritePaths=' + base + '/server-files/logs ' +
            base + '/diagnostics ' + base + '/runtime-test /run/lock\n',
    }


def bootstrap(config):
    check_storage(config)
    base, name = Path(config['base']), config['container']
    env = Path(config.get('game_env_file', '/etc/corekeeper.env'))
    private_file(env)
    ref = Path(config.get('image_ref_file', str(base / 'ops/fex-image-ref')))
    private_file(ref)
    image = ref.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]+@sha256:[a-f0-9]{64}', image):
        raise ValueError('An immutable image digest is required')
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
    if info['Architecture'] != 'arm64' or 'COREKEEPER_RUNTIME=fex' not in info['Config']['Env']:
        raise ValueError('Expected an ARM64 FEX image')
    if subprocess.run(['docker', 'container', 'inspect', name], capture_output=True).returncode == 0:
        raise ValueError('Container already exists; refusing to replace it')
    mounts = [('server-data', '/home/steam/core-keeper-data'),
              ('server-files', '/home/steam/core-keeper-dedicated'),
              ('fex-cache', '/home/steam/.cache/fex'),
              ('mesa-cache', '/home/steam/.cache/mesa_shader_cache'),
              ('update-control', '/run/corekeeper-update')]
    args = ['docker', 'run', '-d', '--name', name, '--restart', 'unless-stopped',
            '--stop-timeout', '120', '--log-driver', 'json-file',
            '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3', '--env-file', str(env)]
    if config.get('memory_limit'):
        args += ['--memory', config['memory_limit'], '--memory-swap', config['memory_limit']]
    if config.get('allow_core_dumps', False):
        args += ['--ulimit', 'core=-1']
    for directory, target in mounts:
        source = base / directory
        if not source.is_dir() or source.is_symlink():
            raise ValueError('Missing or unsafe data directory: ' + str(source))
        args += ['--mount', f'type=bind,src={source},dst={target}']
    # Do not force owner IDs, activation, update gating or a host-wide core policy.
    subprocess.run(args + [image], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'settings', 'check-container', 'dropins', 'bootstrap'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo')
    config = load()
    check_storage(config)
    if args.action == 'settings':
        print(config['base'], config['container'])
    elif args.action == 'check-container':
        check_container(config)
    elif args.action == 'dropins':
        for name, text in dropins(config).items():
            directory = Path('/etc/systemd/system') / (name + '.d')
            directory.mkdir(exist_ok=True)
            (directory / '10-corekeeper-storage.conf').write_text(text)
    elif args.action == 'bootstrap':
        bootstrap(config)


if __name__ == '__main__':
    main()
