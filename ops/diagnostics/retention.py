#!/usr/bin/python3
"""Bound closed logs/evidence only; never restart, truncate or touch saves."""
import argparse
import fcntl
import gzip
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time

BASE = Path('/data/corekeeper')
LOG_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log(?:\.gz)?$')
RECENT = 3600
MIB = 1024**2


def measure(path):
    """Reject symlinks/special files, even nested ones; count allocated bytes."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('Symlink excluded: ' + str(path))
    size, modified = info.st_blocks * 512, info.st_mtime
    if stat.S_ISDIR(info.st_mode):
        for child in path.iterdir():
            child_size, child_time = measure(child)
            size += child_size
            modified = max(modified, child_time)
    elif not stat.S_ISREG(info.st_mode):
        raise ValueError('Special file excluded: ' + str(path))
    return size, modified


def is_open(path, opened):
    return any(item == path or path in item.parents for item in opened)


def open_paths(root):
    result = subprocess.run(['lsof', '-nP', '-F', 'n', '+D', str(root)],
                            capture_output=True, text=True, timeout=40)
    if result.returncode not in (0, 1) or result.stderr.strip():
        raise RuntimeError('Cannot safely inspect open files under ' + str(root))
    return {Path(line[1:]) for line in result.stdout.splitlines()
            if line.startswith('n/')}


def prune(paths, opened, max_age, budget, now, dry=False, max_count=None):
    entries = []
    for path in paths:
        try:
            size, modified = measure(path)
            entries.append((path, size, modified))
        except (OSError, ValueError) as error:
            print('Excluded:', error, flush=True)
    entries.sort(key=lambda item: item[2], reverse=True)
    # Preserve the newest two in each category, including startup evidence.
    protected = {item[0] for item in entries[:2]}
    total, count = sum(item[1] for item in entries), len(entries)
    removed = []
    for path, size, modified in reversed(entries):
        over = total > budget or (max_count is not None and count > max_count)
        if now - modified <= max_age and not over:
            continue
        if path in protected or now - modified < RECENT or is_open(path, opened):
            continue
        if not dry:
            # Refuse deletion if an entry changed during the scan.
            if measure(path) != (size, modified):
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        print(('Would remove:' if dry else 'Removed:'), path, size, 'bytes', flush=True)
        total -= size
        count -= 1
        removed.append(path)
    if total > budget or (max_count is not None and count > max_count):
        print('Protected entries exceed retention target; left intact.', flush=True)
    return removed


def compress_closed_logs(paths, opened, now, dry=False):
    for path in paths:
        if path.suffix != '.log' or path.is_symlink():
            continue
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            continue
        if now - info.st_mtime < RECENT or is_open(path, opened):
            continue
        target = path.with_suffix('.log.gz')
        if target.exists() or target.is_symlink():
            continue
        if dry:
            print('Would compress:', path, flush=True)
            continue
        fd, temporary = tempfile.mkstemp(prefix='.retention-', dir=path.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as output:
                with gzip.GzipFile(filename='', mode='wb', fileobj=output) as archive:
                    with path.open('rb') as source:
                        shutil.copyfileobj(source, archive, 1024 * 1024)
            # Verify the complete gzip stream before removing its source.
            with gzip.open(temporary, 'rb') as source:
                while source.read(1024 * 1024):
                    pass
            after = path.lstat()
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                    info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
                continue
            os.chmod(temporary, 0o600)
            os.chown(temporary, info.st_uid, info.st_gid)
            os.utime(temporary, (info.st_atime, info.st_mtime))
            os.replace(temporary, target)
            path.unlink()
            print('Compressed:', path, flush=True)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0 or not os.path.ismount('/data'):
        raise RuntimeError('Requires root and mounted /data')
    roots = [BASE / 'server-files/logs', BASE / 'diagnostics', BASE / 'runtime-test']
    for root in [BASE, BASE / 'server-files', *roots]:
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError('Unexpected directory: ' + str(root))
    # Serialize with game updates; never race their backup/container recreation.
    with open('/run/lock/corekeeper-update-check.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Maintenance already active; retention skipped.', flush=True)
            return
        opened = set().union(*(open_paths(root) for root in roots))
        now = time.time()
        logs = [p for p in roots[0].iterdir() if LOG_PATTERN.fullmatch(p.name)]
        compress_closed_logs(logs, opened, now, args.dry_run)
        logs = [p for p in roots[0].iterdir() if LOG_PATTERN.fullmatch(p.name)]
        prune(logs, opened, 30 * 86400, 100 * MIB, now, args.dry_run)
        manual = [p for p in roots[1].iterdir()
                  if p.name.startswith('hang-') or
                  re.fullmatch(r'formal-.*-backtrace\.txt', p.name)]
        # Each category gets half the 256-MiB manual-evidence target.
        prune(manual, opened, 14 * 86400, 128 * MIB, now, args.dry_run, 10)
        prune(list(roots[2].iterdir()), opened, 14 * 86400,
              128 * MIB, now, args.dry_run, 10)
        print('Retention complete. Open/recent files and newest two per category protected.', flush=True)


if __name__ == '__main__':
    main()
