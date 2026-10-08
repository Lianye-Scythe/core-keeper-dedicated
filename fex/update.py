#!/usr/bin/python3
"""Check FEX image/game updates hourly; transact at the local maintenance hour.

All world slots AND installed game binaries are backed up for real game rollback.
FEX/Mesa caches and the image's guest RootFS are not archived. No live apt upgrades.
"""
import argparse
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from zoneinfo import ZoneInfo


def run(args, timeout=120, check=True):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=check)
    except subprocess.CalledProcessError as error:
        # Do not log full docker-create arguments, which can contain credentials.
        raise RuntimeError(f'{args[0]} failed: {error.stderr[:1200]}') from None


def log(message):
    print(f'{dt.datetime.now(dt.timezone.utc).isoformat()} {message}', flush=True)


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def inspect_container(name):
    return json.loads(run(['docker', 'inspect', name]).stdout)[0]


def image_fingerprint(image):
    """Ignore build timestamps/labels; include scripts, tools and guest content."""
    info = json.loads(run(['docker', 'image', 'inspect', image]).stdout)[0]
    config = dict(info['Config'])
    config.pop('Labels', None)
    probe = '''set -e
dpkg-query -W -f='${binary:Package}=${Version}\\n' | LC_ALL=C sort
cat /opt/fex-rootfs-source.json
find /home/steam/scripts /opt/depot-downloader -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
'''
    contents = run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint',
                    'bash', image, '-c', probe], timeout=180).stdout
    return hashlib.sha256((json.dumps(config, sort_keys=True) + contents).encode()).hexdigest()


def remote_image_reference(image):
    """Resolve ARM64 manifest metadata without downloading image layers."""
    manifest = json.loads(run(['docker', 'manifest', 'inspect', '--verbose', image], timeout=60).stdout)
    entries = manifest if isinstance(manifest, list) else [manifest]
    descriptors = [entry.get('Descriptor', {}) for entry in entries]
    matches = [item['digest'] for item in descriptors
               if item.get('platform', {}).get('architecture') == 'arm64'
               and item.get('platform', {}).get('os') == 'linux'
               and re.fullmatch(r'sha256:[a-f0-9]{64}', item.get('digest', ''))]
    if len(set(matches)) != 1:
        raise ValueError('Registry must expose exactly one Linux ARM64 manifest')
    repo = image.split('@', 1)[0]
    if ':' in repo.rsplit('/', 1)[-1]:
        repo = repo.rsplit(':', 1)[0]
    return repo + '@' + matches[0]


def discard_equivalent_image(state_dir, image, current, reference):
    """Only remove this repository's unused equivalent candidate; never force."""
    previous = state_dir / 'previous.json'
    if image == current or (previous.exists() and json.loads(previous.read_text())['image'] == image):
        return
    if run(['docker', 'ps', '-aq', '--filter', 'ancestor=' + image]).stdout.strip():
        return
    info = json.loads(run(['docker', 'image', 'inspect', image]).stdout)[0]
    repo = reference.split('@', 1)[0]
    all_refs = (info.get('RepoTags') or []) + (info.get('RepoDigests') or [])
    refs = [ref for ref in all_refs
            if ref.startswith(repo + ':') or ref.startswith(repo + '@')]
    if len(refs) != len(all_refs):
        return  # Another repository/user also references this image.
    if refs:
        run(['docker', 'image', 'rm', *refs], check=False)
    else:
        run(['docker', 'image', 'rm', image], check=False)


def cleanup_owned_images(state_dir, candidate, current):
    """Delete only superseded images this updater pulled, never global prune."""
    owned_path = state_dir / 'owned-images.json'
    owned = set(json.loads(owned_path.read_text())) if owned_path.exists() else set()
    owned.add(candidate)
    previous_path = state_dir / 'previous.json'
    protected = {candidate, current}
    if previous_path.exists():
        protected.add(json.loads(previous_path.read_text())['image'])
    remaining = set()
    for image in owned:
        if image in protected:
            remaining.add(image)
        elif 'No such image:' in run(['docker', 'image', 'inspect', image], check=False).stderr:
            continue
        elif run(['docker', 'image', 'rm', image], check=False).returncode != 0:
            # Docker refuses removal if another container/tag still needs it.
            remaining.add(image)
    atomic_json(owned_path, sorted(remaining))


def valid_build(value):
    # Numeric markers from older deployments trigger a one-time verified upgrade.
    return isinstance(value, str) and re.fullmatch(r'(?:manifest:1963722:)?[0-9]+', value) is not None


def latest_build(container):
    helper = Path(__file__).with_name('steam-build.sh').read_text()
    build = run(['docker', 'exec', container, 'bash', '-c', helper], timeout=180).stdout.strip()
    if not re.fullmatch(r'manifest:1963722:[0-9]+', build):
        raise ValueError('Invalid direct Steam Linux manifest identity')
    return build


def validate_paths(base, mountpoint):
    if not base.is_absolute() or str(base) in ('/', '/home', '/data', '/srv'):
        raise ValueError('An explicit dedicated game directory is required')
    if base.is_symlink() or base.resolve() != base:
        raise ValueError('Game directory must not contain symlink components')
    if not os.path.ismount(mountpoint):
        raise ValueError('Required data mount is absent; refusing system-disk fallback')
    for name in ('server-data', 'server-files', 'fex-cache', 'mesa-cache'):
        directory = base / name
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f'Missing or linked game directory: {directory}')
    for name in ('backups', 'update-control', 'update-state'):
        directory = base / name
        if directory.is_symlink():
            raise ValueError(f'Linked maintenance directory: {directory}')
        directory.mkdir(exist_ok=True)


def environment(info):
    return dict(item.split('=', 1) for item in info['Config']['Env'])


def image_repo_digests(image):
    """Registry pull references, unlike the local Docker image/config ID."""
    info = json.loads(run(['docker', 'image', 'inspect', image]).stdout)[0]
    return sorted({ref for ref in info.get('RepoDigests') or []
                   if isinstance(ref, str) and
                   re.fullmatch(r'[^\s@]+@sha256:[a-f0-9]{64}', ref)})


def replacement_args(info, image, base):
    """Preserve the supported bind-mounted deployment; reject unknown features."""
    host, config = info['HostConfig'], info['Config']
    if host.get('Privileged') or host.get('CapAdd') or host.get('Devices'):
        raise ValueError('Privileged/device configuration is unsupported')
    if host.get('NetworkMode') not in ('default', 'bridge'):
        raise ValueError('Only the default Docker bridge is supported')
    if host.get('AutoRemove') or host.get('ReadonlyRootfs') or config.get('User'):
        raise ValueError('Unsupported auto-remove/read-only/non-root entry configuration')
    if host.get('CpuQuota', 0) > 0 or host.get('CpusetCpus') or host.get('NanoCpus', 0):
        raise ValueError('CPU-constrained deployment needs a custom updater')
    if host.get('SecurityOpt') or host.get('ExtraHosts') or host.get('Dns'):
        raise ValueError('Custom security/host/DNS configuration is unsupported')
    if config.get('Entrypoint') != ['/usr/bin/tini', '--'] or config.get('Cmd') != ['bash', 'scripts/entry.sh']:
        raise ValueError('Custom entrypoint/command configuration is unsupported')
    expected = {
        '/home/steam/core-keeper-data': 'server-data',
        '/home/steam/core-keeper-dedicated': 'server-files',
        '/home/steam/.cache/fex': 'fex-cache',
        '/home/steam/.cache/mesa_shader_cache': 'mesa-cache',
        '/run/corekeeper-update': 'update-control',
    }
    mounted = set()
    for mount in info['Mounts']:
        target = mount['Destination']
        if (target not in expected or mount['Type'] != 'bind' or not mount['RW']
                or mount['Source'] != str(base / expected[target])
                or mount.get('Propagation', 'rprivate') not in ('private', 'rprivate')):
            raise ValueError(f'Unexpected mount: {target}')
        mounted.add(target)
    if not set(expected).difference({'/run/corekeeper-update'}) <= mounted:
        raise ValueError('Required FEX/data mounts are absent')
    env = environment(info)
    if env.get('COREKEEPER_RUNTIME') != 'fex' or env.get('USE_DEPOT_DOWNLOADER') != 'true':
        raise ValueError('Only FEX with native DepotDownloader is supported')
    if not re.fullmatch(r'(?:[0-9]|[12][0-9])', env.get('WORLD_INDEX', '')):
        raise ValueError('Invalid selected world slot')
    env.update(COREKEEPER_RUNTIME='fex', USE_DEPOT_DOWNLOADER='true',
               UPDATE_GATE_ENABLED='true', UPDATE_PERMIT_FILE='/run/corekeeper-update/apply-update',
               ACTIVATE_ALL_CONTENT=env.get('ACTIVATE_ALL_CONTENT', 'false'),
               FEX_MULTIBLOCK=env.get('FEX_MULTIBLOCK', '1'),
               FEX_MAXINST=env.get('FEX_MAXINST', '16'), FEX_SMCCHECKS=env.get('FEX_SMCCHECKS', '1'))
    new_info = json.loads(run(['docker', 'image', 'inspect', image]).stdout)[0]
    if 'COREKEEPER_RUNTIME=fex' not in new_info['Config'].get('Env', []):
        raise ValueError('Candidate image is not FEX')
    old_defaults = json.loads(run(['docker', 'image', 'inspect', info['Image']]).stdout)[0]['Config']['Env']
    defaults = dict(item.split('=', 1) for item in old_defaults)
    required = {'COREKEEPER_RUNTIME', 'USE_DEPOT_DOWNLOADER', 'UPDATE_GATE_ENABLED',
                'UPDATE_PERMIT_FILE', 'ACTIVATE_ALL_CONTENT', 'FEX_MULTIBLOCK',
                'FEX_MAXINST', 'FEX_SMCCHECKS', 'WORLD_INDEX', 'WORLD_NAME', 'GAME_ID'}
    # Refresh image defaults, retain user overrides and validated FEX knobs.
    env = {key: value for key, value in env.items()
           if not key.startswith('BOX64_') and (key in required or defaults.get(key) != value)}
    args = ['docker', 'create', '--name', info['Name'].lstrip('/'),
            '--restart', 'unless-stopped', '--stop-timeout', str(config.get('StopTimeout', 120)),
            '--log-driver', 'json-file', '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3']
    for key, option in (('Memory', '--memory'), ('MemorySwap', '--memory-swap'),
                        ('MemoryReservation', '--memory-reservation'), ('CpuShares', '--cpu-shares')):
        if host.get(key):
            args += [option, str(host[key])]
    for limit in host.get('Ulimits') or []:
        args += ['--ulimit', f"{limit['Name']}={limit['Soft']}:{limit['Hard']}"]
    for port, bindings in (host.get('PortBindings') or {}).items():
        for binding in bindings or []:
            ip = binding.get('HostIp', '')
            args += ['--publish', f"{ip + ':' if ip else ''}{binding['HostPort']}:{port}"]
    for key, value in sorted(env.items()):
        args += ['--env', f'{key}={value}']
    for key, value in (config.get('Labels') or {}).items():
        if not key.startswith('org.opencontainers.image.'):
            args += ['--label', f'{key}={value}']
    for target, source in expected.items():
        args += ['--mount', f'type=bind,src={base / source},dst={target}']
    return args + [image]


def validate_archive(path):
    # Consume the complete gzip stream, including its CRC/trailer, before using
    # tar headers. A readable table of contents alone is not sufficient.
    with gzip.open(path, 'rb') as compressed:
        while compressed.read(1024 * 1024):
            pass
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError('Empty rollback archive')
        roots = set()
        for member in members:
            parts = Path(member.name).parts
            if (not parts or Path(member.name).is_absolute() or '..' in parts
                    or parts[0] not in ('server-data', 'server-files')
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f'Unsafe rollback archive entry: {member.name}')
            roots.add(parts[0])
        if roots != {'server-data', 'server-files'}:
            raise ValueError('Incomplete rollback archive')


def prune_backups(directory, keep):
    for path in sorted(directory.glob('corekeeper-full-*.tar.gz'),
                       key=lambda item: item.name, reverse=True)[keep:]:
        if path.is_file() and not path.is_symlink():
            path.unlink()


def wait_ready(name, helper, timeout):
    started = inspect_container(name)['State']['StartedAt']
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = inspect_container(name)
        if not info['State']['Running'] or info['State']['StartedAt'] != started:
            return False
        if run([helper, name], timeout=60, check=False).returncode == 0:
            return True
        time.sleep(15)
    return False


def restore_archive(backup, base):
    validate_archive(backup)
    stage = Path(tempfile.mkdtemp(prefix='.restore-', dir=base))
    run(['tar', '-xzf', str(backup), '-C', str(stage), '--numeric-owner'], timeout=600)
    for name in ('server-data', 'server-files'):
        failed = stage / (name + '-failed')
        failed.mkdir()
        # Preserve bind-mount directory inodes; move children, never follow links.
        for child in (base / name).iterdir():
            child.rename(failed / child.name)
        for child in (stage / name).iterdir():
            child.rename(base / name / child.name)
    shutil.rmtree(stage)


def maintain(config, force=False):
    base = Path(config['base'])
    validate_paths(base, config['required_mountpoint'])
    name = config['container']
    keep, hour = config.get('backup_keep', 2), config.get('maintenance_hour', 4)
    if keep not in (1, 2) or not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError('Invalid backup retention or maintenance hour')
    state_dir = base / 'update-state'
    transaction = state_dir / 'transaction.json'
    if transaction.exists():
        raise ValueError(f'Unfinished transaction requires manual review: {transaction}')
    info = inspect_container(name)
    if not info['State']['Running']:
        raise ValueError('Server is stopped; do not override an intentional stop')
    build = latest_build(name)
    installed_file = base / 'server-files/.corekeeper-buildid'
    installed = installed_file.read_text().strip() if installed_file.exists() else ''
    if installed and not valid_build(installed):
        raise ValueError('Invalid installed build marker')
    reference = remote_image_reference(config['image'])
    equivalent_path = state_dir / 'equivalent-image.json'
    equivalent = json.loads(equivalent_path.read_text()) if equivalent_path.exists() else {}
    reuse = equivalent.get('reference') == reference and equivalent.get('current_image') == info['Image']
    if reuse:
        candidate = info['Image']
    else:
        run(['docker', 'pull', reference], timeout=600)
        candidate = json.loads(run(['docker', 'image', 'inspect', reference]).stdout)[0]['Id']
    cache_path = state_dir / 'fingerprints.json'
    fingerprints = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for image in {info['Image'], candidate}:
        if image not in fingerprints:
            fingerprints[image] = image_fingerprint(image)
    atomic_json(cache_path, {image: fingerprints[image] for image in {info['Image'], candidate}})
    image_changed = fingerprints[info['Image']] != fingerprints[candidate]
    if not image_changed and candidate != info['Image']:
        atomic_json(equivalent_path, dict(reference=reference, current_image=info['Image']))
        discard_equivalent_image(state_dir, candidate, info['Image'], reference)
        candidate = info['Image']
    elif image_changed:
        equivalent_path.unlink(missing_ok=True)
    game_changed = installed != build
    migration = not any(m['Destination'] == '/run/corekeeper-update' for m in info['Mounts'])
    args = replacement_args(info, candidate, base)  # Validate before stopping.
    env = environment(info)
    uid, gid = int(env.get('PUID', 1000)), int(env.get('PGID', 1000))
    if uid <= 0 or gid <= 0:
        raise ValueError('Container owner IDs must be positive')
    os.chown(base / 'update-control', uid, gid)
    os.chmod(base / 'update-control', 0o775)
    if not (game_changed or image_changed or migration):
        (state_dir / 'pending.json').unlink(missing_ok=True)
        cleanup_owned_images(state_dir, candidate, info['Image'])
        log(f'No content update; game build {build}, FEX image unchanged. No restart.')
        return
    pending = dict(game_build=build, image=candidate, image_changed=image_changed,
                   game_changed=game_changed, gate_mount_migration=migration)
    atomic_json(state_dir / 'pending.json', pending)
    zone = ZoneInfo(config.get('timezone', 'UTC'))
    if not force and dt.datetime.now(zone).hour != hour:
        log(f'Queued changes for the next {zone.key} {hour:02}:00: {pending}')
        return
    helper = config['readiness_helper']
    if not os.access(helper, os.X_OK):
        raise ValueError('Readiness helper is absent or not executable')
    timestamp = dt.datetime.now(zone).strftime('%Y%m%d-%H%M%S')
    rollback = name + '-rollback-' + timestamp
    backup = base / 'backups' / f'corekeeper-full-{timestamp}.tar.gz'
    permit = base / 'update-control/apply-update'
    old_policy = info['HostConfig']['RestartPolicy']['Name'] or 'no'
    previous_digests = image_repo_digests(info['Image'])
    atomic_json(transaction, dict(container=name, rollback=rollback, backup=str(backup),
                                 previous_image=info['Image'],
                                 previous_repo_digests=previous_digests, **pending))
    renamed = backup_valid = False
    try:
        run(['docker', 'update', '--restart=no', name])
        run(['docker', 'stop', '--time', '120', name], timeout=150)
        run(['tar', '--numeric-owner', '-czf', str(backup), '-C', str(base),
             'server-data', 'server-files'], timeout=600)
        validate_archive(backup)
        backup_valid = True
        log(f'Verified full rollback backup: {backup}')
        run(['docker', 'rename', name, rollback])
        renamed = True
        if game_changed:
            permit.write_text(str(int(time.time())) + '\n')
            os.chmod(permit, 0o644)
        else:
            permit.unlink(missing_ok=True)
        run(args)
        run(['docker', 'start', name])
        if not wait_ready(name, helper, config.get('readiness_timeout', 1200)):
            raise RuntimeError('Replacement did not reach simulation-ready state')
        observed = installed_file.read_text().strip() if installed_file.exists() else ''
        if observed != build:
            raise RuntimeError(f'Installed build uncertified: {observed!r}, expected {build}')
    except Exception:
        permit.unlink(missing_ok=True)
        if renamed:
            exists = run(['docker', 'inspect', name], check=False).returncode == 0
            if exists:
                run(['docker', 'stop', '--time', '120', name], timeout=150, check=False)
                run(['docker', 'rm', '-f', name])
            if backup_valid:
                restore_archive(backup, base)
            run(['docker', 'rename', rollback, name])
        run(['docker', 'update', '--restart=' + old_policy, name])
        run(['docker', 'start', name])
        if not wait_ready(name, helper, config.get('readiness_timeout', 1200)):
            raise RuntimeError('Rollback did not become ready; transaction journal retained')
        transaction.unlink()
        if backup_valid:
            prune_backups(base / 'backups', keep)
        elif backup.exists():
            backup.unlink()
        log('Update failed; restored previous FEX container and pre-update game/save files.')
        raise

    # Commit/cleanup is outside rollback scope: never try to restore a container
    # after it has been removed. Errors here leave the journal for manual review.
    atomic_json(state_dir / 'installed.json', dict(game_build=observed, image=candidate,
                fingerprint=fingerprints[candidate], updated_at=dt.datetime.now(zone).isoformat()))
    atomic_json(state_dir / 'previous.json', dict(image=info['Image'], backup=str(backup),
                                                repo_digests=previous_digests))
    prune_backups(base / 'backups', keep)
    permit.unlink(missing_ok=True)
    if (base / 'ops/fex-image-ref').exists():
        refs = json.loads(run(['docker', 'image', 'inspect', candidate]).stdout)[0].get('RepoDigests') or []
        if refs:
            (base / 'ops/fex-image-ref').write_text(refs[0] + '\n')
    run(['docker', 'rm', rollback])
    transaction.unlink()
    (state_dir / 'pending.json').unlink(missing_ok=True)
    cleanup_owned_images(state_dir, candidate, candidate)
    log(f'Updated build {observed}; retained at most {keep} full backups. Client join not tested.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Explicitly apply outside the maintenance hour')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo/root')
    os.umask(0o077)
    config_path = Path(os.environ.get('COREKEEPER_UPDATE_CONFIG', '/etc/corekeeper-update-check.json'))
    stat = config_path.stat()
    if stat.st_uid != 0 or stat.st_mode & 0o022 or config_path.is_symlink():
        raise ValueError('Configuration must be root-owned, non-linked and not group/world writable')
    with open('/run/lock/corekeeper-update-check.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('Another update check is running; skipped.')
            return
        maintain(json.loads(config_path.read_text()), args.force)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        log(f'Maintenance error: {error}')
        sys.exit(1)
