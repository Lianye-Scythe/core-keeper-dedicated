# Optional host diagnostics

These tools are **optional**, installed on the host rather than inside the game
image. They observe one configured rootful Docker container. Paths and the
container name come from a shared private host configuration, not a specific
Oracle instance. No private environment files, Game IDs, dumps or raw logs are
included. Full kernel-core routing remains Ubuntu/Apport-specific.

## Shared host configuration

Deployment, maintenance and diagnostics use `/etc/corekeeper-update-check.json`.
If the updater is already configured, **preserve that file**. Otherwise prepare
it from the repository root:

```sh
sudo install -m 0600 examples/scheduled-updates/corekeeper-update-check.json.example /etc/corekeeper-update-check.json
sudoedit /etc/corekeeper-update-check.json
sudo python3 -B ops/diagnostics/host_config.py check
```

Confirm these settings before installation; creating this file does not enable
an update timer or start a game:

| Setting | Example / default | Used by |
| --- | --- | --- |
| `base` | `/srv/corekeeper` | All host tools; must match game bind sources |
| `container` | `core-keeper-dedicated` | All host tools |
| `required_mountpoint` | `/` for system-disk quick start | All host tools; use the real separate disk mount when applicable |
| `timezone`, `maintenance_hour` | `UTC`, `4` | Updater only; choose your preferred window |
| `game_env_file` | `/etc/corekeeper.env` when omitted | Optional bootstrap only |
| `image_ref_file` | `<base>/ops/fex-image-ref` when omitted | Optional bootstrap only |
| `memory_limit` | Omitted: no imposed cap | Optional bootstrap only; e.g. `10g`, also disables container swap |
| `allow_core_dumps` | Omitted: `false` | Optional bootstrap only; `true` adds `--ulimit core=-1` |

Host settings must be root-owned regular files with mode `0600`. Paths must be
absolute and normalized without whitespace or shell/systemd escapes. The game
base, its ancestors and managed storage directories must not be symlinks.
Use a dedicated game directory, not a filesystem root. The installer
checks that the configured container's save/game mounts match the base directory.
It generates systemd storage dependencies and narrowly scoped writable-path
drop-ins from these settings. Do not install the bare unit templates alone.

After changing storage settings, stop observers, update the configuration and
rerun the installer to regenerate drop-ins before observing the new deployment.
Do not replace host settings or helpers during active game maintenance. Installing
new sources does not move data or change the running game's configuration.

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
`curl`, `lsof`, and the configured mounted layout. The game must already have created
`<base>/server-files/logs`; the installer does not initialize/reset worlds.
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
disk after a mount failure when a separate disk mount is configured. Default units enable at boot; no notification service
or game health watchdog is installed.

## Optional full core routing — host-wide change

Use only after reviewing existing Ubuntu Apport policy. This opt-in supports the
existing Apport pipe and its supported placeholders; it refuses to replace a
different crash handler. It saves the current core pattern/positive pipe limit
in a root-private configuration, forwards non-target cores to the original Apport
command, and targets the game by command line **and the device/inode of its
save-directory bind mount**.

```sh
sudo bash ops/diagnostics/install.sh --enable-core-routing
```

This changes `kernel.core_pattern` globally and persists it in
`/etc/sysctl.d/90-corekeeper-crash.conf`. The router requires a kernel supporting
the `%F` pidfd placeholder (validated on Ubuntu 26.04); do not deploy it
blindly on older kernels. It keeps the existing positive `core_pipe_limit` rather
than guessing a new host policy. The timeout also bounds forwarded Apport calls.
A game core is not guaranteed: Unity may handle a signal itself, Docker may kill
the process, or space/timeout limits may prevent capture.

The container must also allow kernel cores. Add `--ulimit core=-1` to Docker run,
or the following to the Compose service, then recreate it during planned downtime
to apply the setting. For the optional bootstrap, explicitly set
`allow_core_dumps=true` in host configuration. For Compose:

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

Private output lives under `<base>/diagnostics` and optional manual
trial output under `<base>/runtime-test`. View service errors with:

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
saves, backups, caches or the independent update timer. Historical test results
are preserved separately in `fex/RESULTS.md`; raw trial artifacts are not public.
