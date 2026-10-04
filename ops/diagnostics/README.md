# Optional managed-host diagnostics

These are source versions of the observers used on the managed Oracle A1 host.
They are **optional**, installed on the host rather than inside the game image,
and deliberately support one rootful Docker container named
`core-keeper-dedicated` under `/data/corekeeper` on a mounted `/data` disk.
Changing paths/container names requires reviewing scripts and unit files together;
the scheduled updater itself supports a configurable base, but these templates do
not. No private host environment files, Game IDs, dumps or raw logs are included.

## What each component does

| Component | Behaviour | Retention / safety limits |
| --- | --- | --- |
| `crash-evidence.py` | Observe abnormal Docker exits; optionally collect kernel cores and mapped executable libraries. | Two `crash-*` bundles; compressed core up to 2 GiB, raw input up to 16 GiB, mapped binaries up to 768 MiB raw; skip/stop core collection below 6 GiB free; core handler timeout 180 s. |
| `network-evidence.py` | Sample host/container connectivity and game CPU/RSS every 15 s; capture context around log errors or repeated multi-endpoint failures. | Two rotating 8-MiB sample logs; two incidents, bounded log tails/events and context windows; two-minute cooldown. |
| `retention.py` | Compress inactive timestamped game logs, prune old logs and selected manual/test evidence hourly. | Logs: 30 days / 100 MiB target. Manual `hang-*`/`formal-*-backtrace.txt`: 14 days / 128 MiB / 10 entries. `runtime-test`: another 14 days / 128 MiB / 10 entries. |

The two-manual-category combined target is 256 MiB. Retention preserves open
files/directories containing open files, entries modified within one hour and
the newest two per category. Symlinks/special files are excluded. **These are
soft retention targets, not filesystem quotas**: protected files can exceed
them and produce journal warnings. An active game log is never truncated.
Crash/runtime archive size limits do not establish a total disk quota for every
piece of metadata. Timeout/space/size limits may leave no usable full core.

The retention job shares the updater's maintenance lock and skips active
maintenance. It never touches saves, world backups, automatic `crash-*` bundles
or network evidence; the automatic collectors manage their own retention.
Game Docker log rotation is separate (the deployment examples use 10 MiB × 3).
Host system journals and other services are outside this suite's cleanup scope.

No component sends notifications, changes FEX settings, or restarts the game.
Network probing adds small ongoing CPU/network work; crash compression consumes
CPU/I/O and can delay process cleanup/restart. Diagnose before assuming a fault
is in the translator: a dump usually identifies the detection point, not the
origin of corruption. HTTP/TCP success does not prove Steam UDP relay health.

## Install observers and retention

Prerequisites: root access, systemd, rootful Docker, Python 3.10+, GNU `timeout`,
`curl`, `lsof`, and the mounted managed layout. The game must already have created
`/data/corekeeper/server-files/logs`; the installer does not initialize/reset worlds.
Run from the repository root:

```sh
sudo apt-get install python3 curl lsof coreutils
sudo bash ops/diagnostics/install.sh
systemctl status corekeeper-crash-evidence.service corekeeper-network-evidence.service
systemctl list-timers corekeeper-diagnostics-retention.timer
sudo /usr/local/libexec/corekeeper-diagnostics-retention --dry-run
```

Installation enables the observers and hourly timer, and restarts **only the
observer services** to apply newer scripts. It does not recreate/restart the
game. The timer can prune eligible old evidence at its next run; preview your
existing data with `sudo python3 -B ops/diagnostics/retention.py --dry-run` before
installing if needed. The default install captures exit/network evidence but
does **not** change the host's global kernel core handler.

Never install from an untrusted checkout as root. The script keeps private
diagnostic directories root-owned (0700), files 0600, and leaves game-log directory
ownership alone. It requires the separate data mount to avoid filling the root
disk after a mount failure. Default units enable at boot; no notification service
or game health watchdog is installed.

## Optional full core routing — host-wide change

Use only after reviewing existing Ubuntu Apport policy. This opt-in supports the
existing Apport pipe and its supported placeholders; it refuses to replace a
different crash handler. It saves the current core pattern/positive pipe limit
in a root-private configuration, forwards non-target cores to the original Apport
command, and targets the game by command line **and the device/inode of its
save-directory bind mount**. The current managed host uses this routing.

```sh
sudo bash ops/diagnostics/install.sh --enable-core-routing
```

This changes `kernel.core_pattern` globally and persists it in
`/etc/sysctl.d/90-corekeeper-crash.conf`. The router requires a kernel supporting
the `%F` pidfd placeholder, as on the managed Ubuntu 26.04 host; do not deploy it
blindly on older kernels. It keeps the existing positive `core_pipe_limit` rather
than guessing a new host policy. The timeout also bounds forwarded Apport calls.
A game core is not guaranteed: Unity may handle a signal itself, Docker may kill
the process, or space/timeout limits may prevent capture.

The container must also allow kernel cores. Add `--ulimit core=-1` to Docker run,
or the following to the Compose service, then recreate it during planned downtime
to apply the setting. The managed bootstrap already supplies it:

```yaml
ulimits:
  core:
    soft: -1
    hard: -1
```

The installer does not change the game's ulimit or restart it. Changing the
kernel route is immediate; a missing container ulimit requires recreation.
Inspect `core-result.json` and `runtime-index.json` before treating an archive as
complete. Guest anonymous JIT code is not reconstructed simply from mapped library
files; full diagnosis may require matching FEX/game debug symbols and expert review.

## Read evidence safely

Private output lives under `/data/corekeeper/diagnostics` and optional manual
trial output under `/data/corekeeper/runtime-test`. View service errors with:

```sh
sudo journalctl -u corekeeper-crash-evidence.service -n 50 --no-pager
sudo journalctl -u corekeeper-network-evidence.service -n 50 --no-pager
sudo journalctl -u corekeeper-diagnostics-retention.service -n 50 --no-pager
```

Do not publish raw cores, Docker metadata, save files, logs or environment
configuration. They may contain join IDs, passwords, API keys, player details,
network addresses and memory-resident secrets. Git-ignore rules are only an
accidental-commit safeguard, not a substitute for checking staged files.
Synthetic tests under `tests/` do not read live host data or generate real cores.

## Disable / rollback without deleting evidence

```sh
sudo systemctl disable --now corekeeper-crash-evidence.service corekeeper-network-evidence.service corekeeper-diagnostics-retention.timer
```

If full routing was enabled, disabling services **does not restore the kernel
route**. Stop the observers first. Inspect the saved root-private configuration,
then restore `original_core_pattern` and `original_core_pipe_limit` using the
host's `sysctl` tooling and remove only
`/etc/sysctl.d/90-corekeeper-crash.conf`. Keep the saved configuration and router
binary until restoration is confirmed. Do not delete the router executable while
the kernel still points at it. If another administrator changed crash policy
since installation, review rather than overwrite their changes.

Disabling the timer leaves diagnostic files intact and does not affect game
saves, backups, caches or the independent update timer. Historical trial artifact
paths in `fex/RESULTS.md` may no longer exist after retention; the report itself
is preserved as historical evidence.
