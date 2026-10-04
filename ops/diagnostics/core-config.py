#!/usr/bin/python3
"""Validate an existing Apport pipe before opting into global core routing."""
import argparse
import json
from pathlib import Path
import re
import shlex

ROUTED_PATTERN = '|/usr/local/sbin/corekeeper-core-router %P %p %s %t %u %g %c %d %F %E'
CONFIG = Path('/etc/corekeeper-crash-router.json')
SYSCTL = Path('/etc/sysctl.d/90-corekeeper-crash.conf')


def make_config(pattern, limit):
    if not pattern.startswith('|/usr/share/apport/apport '):
        raise ValueError('Only an existing Ubuntu Apport pipe is supported; refusing to replace another handler')
    argv = shlex.split(pattern[1:])
    supported = set('PpstugcdFE')
    for token in argv:
        if any(item not in supported for item in re.findall(r'%(.)', token)):
            raise ValueError('Apport uses an unsupported kernel placeholder')
    limit = int(limit)
    if limit < 1:
        raise ValueError('A positive core_pipe_limit is required for /proc evidence; review host policy first')
    return {'apport_argv': argv, 'original_core_pattern': pattern,
            'original_core_pipe_limit': limit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without writing host configuration')
    args = parser.parse_args()
    pattern = Path('/proc/sys/kernel/core_pattern').read_text().strip()
    limit = Path('/proc/sys/kernel/core_pipe_limit').read_text().strip()
    if pattern == ROUTED_PATTERN:
        if not CONFIG.is_file() or CONFIG.is_symlink() or not SYSCTL.is_file() or SYSCTL.is_symlink():
            raise ValueError('Router is active without a complete saved configuration; manual review required')
        saved = json.loads(CONFIG.read_text())
        if make_config(saved['original_core_pattern'], saved['original_core_pipe_limit']) != saved:
            raise ValueError('Saved router configuration is inconsistent')
        return
    if CONFIG.exists() or CONFIG.is_symlink() or SYSCTL.exists() or SYSCTL.is_symlink():
        raise ValueError('A previous router configuration exists; review it before replacing anything')
    config = make_config(pattern, limit)
    if not args.check:
        # Exclusive creation prevents overwriting another administrator's files.
        with CONFIG.open('x') as stream:
            stream.write(json.dumps(config, indent=2) + '\n')
        CONFIG.chmod(0o600)
        with SYSCTL.open('x') as stream:
            stream.write('kernel.core_pattern=' + ROUTED_PATTERN + '\n'
                         'kernel.core_pipe_limit=' + str(config['original_core_pipe_limit']) + '\n')
        SYSCTL.chmod(0o600)


if __name__ == '__main__':
    main()
