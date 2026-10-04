#!/usr/bin/python3
"""Startup readiness for loaded or freshly generated worlds; not a client probe."""
import json
import re
import subprocess
import sys


def logs_ready(logs):
    session = logs.find('Started session with info:')
    if session < 0:
        return False
    markers = (
        'successfully loaded world file into SerializeWorld',
        'starting a new world :',
    )
    positions = [logs.find(marker, session) for marker in markers]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return False
    return re.search(r'\btimescale = [01](?:\s|$)', logs[min(positions):]) is not None


def command(args):
    return subprocess.run(args, capture_output=True, timeout=20, check=True)


def main():
    container = sys.argv[1] if len(sys.argv) > 1 else 'core-keeper-dedicated'
    inspect = ['docker', 'inspect', '--format', '{{json .State}}', container]
    try:
        before = json.loads(command(inspect).stdout)
        if not before.get('Running'):
            return 1
        result = command(['docker', 'logs', '--timestamps', '--since',
                          before['StartedAt'], '--tail', '2000', container])
        logs = (result.stdout + result.stderr).decode(errors='replace')
        after = json.loads(command(inspect).stdout)
        return 0 if (logs_ready(logs) and after.get('Running')
                     and after['StartedAt'] == before['StartedAt']) else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return 1


if __name__ == '__main__':
    sys.exit(main())
