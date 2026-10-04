#!/usr/bin/python3
"""Bounded network/CPU evidence. Observe only: never restart or modify the game."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ipaddress
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

BASE = Path('/data/corekeeper/diagnostics/network')
CONTAINER = 'core-keeper-dedicated'
INTERVAL = 15
LOG_CAP = 8 * 1024**2
TAIL_CAP = 128 * 1024
TICKS = os.sysconf('SC_CLK_TCK')
PATTERN = re.compile(r'Remote_Timeout|Misc_Timeout|Misc_P2P_Rendezvous|'
                     r'ConnectionDisconnected\(|Connectivity test: result=Failed|SteamNet Error:')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def command(args, timeout=7):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as error:
        return -1, b'', str(error).encode()


def private_write(path, value):
    path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2))
    path.chmod(0o600)


def tail(path, limit=TAIL_CAP):
    with path.open('rb') as f:
        f.seek(max(0, path.stat().st_size - limit))
        return f.read(limit).decode(errors='replace')


def retain_incidents(base):
    paths = sorted((p for p in base.glob('incident-*') if p.is_dir() and not p.is_symlink()),
                   key=lambda p: p.name, reverse=True)
    for old in paths[2:]:
        shutil.rmtree(old)


def append_sample(base, sample):
    path = base / 'samples.jsonl'
    line = json.dumps(sample, separators=(',', ':')) + '\n'
    if path.exists() and path.stat().st_size + len(line.encode()) > LOG_CAP:
        path.replace(base / 'samples.previous.jsonl')
    with path.open('a') as f:
        f.write(line)
    path.chmod(0o600)


def inspect():
    code, out, _ = command(['docker', 'inspect', '--format',
                           '{"id":"{{.Id}}","restarts":{{.RestartCount}},"state":{{json .State}}}',
                           CONTAINER])
    if code:
        return {'error': 'docker inspect unavailable'}
    try:
        return json.loads(out)
    except ValueError:
        return {'error': 'invalid container state'}


def curl_probe(url, expected, container=False):
    args = ['curl', '--noproxy', '*', '--silent', '--show-error', '--connect-timeout', '2',
            '--max-time', '3', '--output', '/dev/null', '--write-out',
            '%{http_code} %{remote_ip} %{time_namelookup} %{time_connect} %{time_total}', url]
    if container:
        args = ['docker', 'exec', CONTAINER] + args
    code, out, err = command(args)
    fields = out.decode(errors='replace').split()
    return {'ok': code == 0 and bool(fields) and fields[0] == str(expected),
            'exit': code, 'metrics': fields, 'error': err.decode(errors='replace')[-256:]}


def cm_endpoint(log):
    matches = re.findall(r'ConnectionCompleted\(\) \(([0-9.]+):([0-9]+),', log)
    if not matches:
        return None
    ip, port = matches[-1]
    try:
        ipaddress.IPv4Address(ip)
        port = int(port)
        return (ip, port) if 1 <= port <= 65535 else None
    except ValueError:
        return None


def tcp_probe(endpoint):
    if not endpoint:
        return {'ok': None, 'error': 'No current Steam CM IPv4 endpoint recorded'}
    started = time.monotonic()
    try:
        with socket.create_connection(endpoint, timeout=2):
            return {'ok': True, 'endpoint': endpoint,
                    'connect_ms': round((time.monotonic() - started) * 1000, 2)}
    except OSError as error:
        return {'ok': False, 'endpoint': endpoint, 'error': str(error)[:256]}


class Reader:
    def __init__(self):
        self.path = None
        self.inode = None
        self.offset = 0

    def read(self, path):
        try:
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            # Prime at EOF: existing historical errors must not trigger new incidents.
            if path != self.path or identity != self.inode:
                self.path, self.inode, self.offset = path, identity, info.st_size
                return ''
            if info.st_size < self.offset:
                self.offset = 0
            start = max(self.offset, info.st_size - TAIL_CAP)
            with path.open('rb') as f:
                f.seek(start)
                data = f.read(TAIL_CAP)
                self.offset = f.tell()
            return data.decode(errors='replace')
        except OSError:
            return ''


def stat_ticks(path):
    text = path.read_text()
    fields = text[text.rfind(')') + 2:].split()
    return int(fields[11]) + int(fields[12]), fields[0]


class LoadSampler:
    def __init__(self):
        self.previous = {}
        self.when = None
        self.pid = None

    def collect(self, pid):
        now = time.monotonic()
        elapsed = now - self.when if self.when and self.pid == pid else None
        current = {}
        result = {'pid': pid}
        if not pid:
            self.previous, self.when, self.pid = {}, now, None
            return result
        proc = Path('/proc') / str(pid)
        try:
            current['process'], _ = stat_ticks(proc / 'stat')
            if elapsed and 'process' in self.previous:
                result['cpu_pct'] = round(100 * (current['process'] - self.previous['process']) / TICKS / elapsed, 2)
            status = (proc / 'status').read_text()
            result['rss_kib'] = int(re.search(r'VmRSS:\s+(\d+)', status).group(1))
            threads = []
            for entry in (proc / 'task').iterdir():
                try:
                    ticks, state = stat_ticks(entry / 'stat')
                    current[entry.name] = ticks
                    cpu = (100 * (ticks - self.previous[entry.name]) / TICKS / elapsed
                           if elapsed and entry.name in self.previous else None)
                    threads.append({'tid': int(entry.name), 'cpu_pct': round(cpu, 2) if cpu is not None else None,
                                    'state': state, 'name': (entry / 'comm').read_text().strip()})
                except OSError:
                    continue
            threads.sort(key=lambda t: t['cpu_pct'] or 0, reverse=True)
            result['thread_count'] = len(threads)
            result['top_threads'] = threads[:4]
            for thread in result['top_threads']:
                try:
                    thread['wait_channel'] = (proc / 'task' / str(thread['tid']) / 'wchan').read_text().strip()
                except OSError:
                    pass
        except (OSError, AttributeError, ValueError) as error:
            result['error'] = str(error)[:256]
        self.previous, self.when, self.pid = current, now, pid
        return result


def game_pid():
    code, out, _ = command(['docker', 'top', CONTAINER, '-eo', 'pid,comm'])
    if code:
        return None
    for line in out.decode(errors='replace').splitlines()[1:]:
        parts = line.split()
        if len(parts) == 2 and parts[1].startswith('CoreKeeper'):
            return int(parts[0])
    return None


def log_paths(state):
    root = Path('/proc') / str(state.get('state', {}).get('Pid', 0)) / 'root'
    steam = root / 'home/steam/Steam/logs'
    logs = list(Path('/data/corekeeper/server-files/logs').glob('*.log'))
    paths = {'steam-connectivity': steam / 'connection_log.txt',
             'steam-cm': steam / 'connection_log_27015.txt'}
    if logs:
        paths['game'] = max(logs, key=lambda p: p.stat().st_mtime)
    return paths


def network_failed(probes):
    def failed(key):
        return probes.get(key, {}).get('ok') is False
    return ((failed('google') and failed('cloudflare'))
            or (failed('steam-host') and failed('steam-container'))
            or (failed('steam-cm-tcp') and failed('steam-host')))


def maintenance_active(path=Path('/run/lock/corekeeper-update-check.lock')):
    try:
        with path.open('r') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True
    except FileNotFoundError:
        return False
    except OSError:
        return None


class Recorder:
    def __init__(self):
        self.ring = deque(maxlen=21)
        self.active = None
        self.deadline = 0
        self.started = 0
        self.cooldown = 0
        self.events = []

    def snapshot(self, path, paths):
        path.mkdir(mode=0o700, exist_ok=True)
        for name, source in paths.items():
            try:
                private_write(path / (name + '.log'), tail(source))
            except OSError as error:
                private_write(path / (name + '.error'), str(error))
        code, out, err = command(['docker', 'inspect', CONTAINER])
        private_write(path / 'container.json', out[-256 * 1024:].decode(errors='replace'))
        for name, args in [('kernel.log', ['journalctl', '-k', '--since', '-5min', '-n', '100', '--no-pager']),
                           ('network-service.log', ['journalctl', '-u', 'systemd-networkd', '-u',
                            'systemd-resolved', '--since', '-5min', '-n', '100', '--no-pager'])]:
            code, out, err = command(args)
            private_write(path / name, (out + err)[-TAIL_CAP:].decode(errors='replace'))

    def observe(self, sample, events, paths):
        now = time.monotonic()
        self.ring.append(sample)
        append_sample(BASE, sample)
        if events and (self.active or now >= self.cooldown):
            if self.active is None:
                self.active = BASE / ('incident-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
                self.active.mkdir(mode=0o700)
                retain_incidents(BASE)
                self.started = now
                self.events = []
                self.snapshot(self.active / 'before', paths)
                print('Network incident started: ' + str(self.active), flush=True)
            self.events.extend({'observed_utc': sample['utc'], **event} for event in events)
            self.events = self.events[-100:]
            self.deadline = min(now + 60, self.started + 120)
        if self.active:
            private_write(self.active / 'events.json', self.events)
            # The ring is bounded even if an extended incident is ongoing.
            existing = self.active / 'window.jsonl'
            if not existing.exists():
                private_write(existing, ''.join(json.dumps(s) + '\n' for s in self.ring))
            else:
                with existing.open('a') as f:
                    f.write(json.dumps(sample) + '\n')
            if now >= self.deadline:
                self.snapshot(self.active / 'after', paths)
                private_write(self.active / 'complete.json', {'completed_utc': stamp(),
                              'note': 'HTTP and TCP probes are diagnostics, not proof of game relay/UDP health.'})
                print('Network incident completed: ' + str(self.active), flush=True)
                self.active = None
                self.cooldown = now + 120


def run(once=False):
    if not os.path.ismount('/data'):
        raise RuntimeError('/data is not mounted')
    os.umask(0o077)
    BASE.mkdir(parents=True, mode=0o700, exist_ok=True)
    BASE.chmod(0o700)
    recorder, load = Recorder(), LoadSampler()
    readers = {}
    previous_id = None
    consecutive_failures = 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        while True:
            began = time.monotonic()
            state = inspect()
            paths = log_paths(state)
            if state.get('id') != previous_id:
                readers = {}
                previous_id = state.get('id')
                load = LoadSampler()
            events = []
            for name, path in paths.items():
                reader = readers.setdefault(name, Reader())
                lines = reader.read(path).splitlines()
                events.extend({'source': name, 'line': line[:512]} for line in lines if PATTERN.search(line))
            cm_log = ''
            try:
                cm_log = tail(paths['steam-cm'])
            except OSError:
                pass
            jobs = {
                'google': pool.submit(curl_probe, 'https://www.google.com/generate_204', 204),
                'cloudflare': pool.submit(curl_probe, 'https://www.cloudflare.com/cdn-cgi/trace', 200),
                'steam-host': pool.submit(curl_probe, 'http://steamconnecttest.com/204', 204),
                'steam-cm-tcp': pool.submit(tcp_probe, cm_endpoint(cm_log)),
            }
            if state.get('state', {}).get('Running'):
                jobs['steam-container'] = pool.submit(curl_probe, 'http://steamconnecttest.com/204', 204, True)
            sample = {'utc': stamp(), 'container': state, 'host_load': os.getloadavg(),
                      'maintenance_active': maintenance_active(),
                      'game': load.collect(game_pid()),
                      'probes': {name: future.result() for name, future in jobs.items()}}
            consecutive_failures = consecutive_failures + 1 if network_failed(sample['probes']) else 0
            if consecutive_failures == 2:
                events.append({'source': 'native-probes', 'line': 'Two consecutive multi-endpoint failures'})
            recorder.observe(sample, events[:100], paths)
            if once:
                print(json.dumps(sample))
                return
            time.sleep(max(1, INTERVAL - (time.monotonic() - began)))


if __name__ == '__main__':
    run(once='--once' in sys.argv)
