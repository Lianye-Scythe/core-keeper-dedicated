# Scheduled maintenance

The [host updater](../fex/update.py) checks hourly and applies detected changes at
**04:00 UTC** with the example configuration.
Both the timezone and maintenance hour are configurable; this is not an automatic
feature of pulling the image or starting Compose. There is no restart when game build and image contents are
unchanged. Image comparison includes installed packages, scripts, downloader and
guest RootFS provenance; rebuild timestamps/labels alone are ignored.

The updater supports the documented rootful Docker deployment with default bridge
network and the five bind mounts. It preserves the Game ID, selected world, name,
user overrides, memory limits and published ports. Unsupported configurations are
rejected before stopping the server rather than silently discarded.

## Installation

Run the helper-install commands from the **repository root**, not from
`docker-compose-example`. Use a recent checkout and the existing deployment's
real paths. Do not run a second updater against the same world or replace host
helpers during an active transaction.

1. Set `UPDATE_GATE_ENABLED=true` and bind a writable
   `update-control` directory to `/run/corekeeper-update`. Ensure its ownership
   matches `PUID`/`PGID`.
   For Compose, edit `core.env` and use `docker compose up -d` to apply changed
   environment variables; `docker restart` alone does not change them. This may
   recreate the container and cause downtime, but does not reset its bind-mounted
   saves. Set up the remaining host steps in the same installation session.
2. Install the helpers (these commands are also used for helper upgrades):

```sh
sudo install -d /usr/local/libexec/corekeeper
sudo install -m 0755 fex/readiness.py /usr/local/libexec/corekeeper-ready
sudo install -m 0644 fex/update.py /usr/local/libexec/corekeeper/update.py
sudo install -m 0755 examples/scheduled-updates/corekeeper-update-check /usr/local/sbin/
sudo install -m 0644 examples/scheduled-updates/corekeeper-update-check.{service,timer} /etc/systemd/system/
```

3. For a **first installation**, create the private JSON only if it is absent.
   Existing files and symlinks are left untouched; inspect unexpected symlinks
   rather than replacing them. Do not run this step to reset an existing host:

```sh
if ! sudo test -e /etc/corekeeper-update-check.json && ! sudo test -L /etc/corekeeper-update-check.json; then
  sudo install -m 0600 examples/scheduled-updates/corekeeper-update-check.json.example /etc/corekeeper-update-check.json
fi
sudoedit /etc/corekeeper-update-check.json
```

   Set the real base directory and the
   mounted filesystem it lives on (`required_mountpoint`, e.g. `/data`). Also
   confirm `container`, `timezone` and `maintenance_hour` explicitly. For example,
   Taiwan 17:00 uses `timezone=Asia/Taipei` and `maintenance_hour=17`; the public
   example's 04:00 UTC is just an example, not a required time. It must
   already contain all four data/cache directories. Host dependencies are Python
   3.10+, Docker, GNU tar and systemd; the image has the download dependencies.
   `required_mountpoint` must be an actual mounted filesystem, **not merely a
   directory**. On the managed separate data disk, use `base=/data/corekeeper`
   and `required_mountpoint=/data`; change every Compose bind source accordingly.
   For the quick-start directory on the system filesystem, the example uses
   `base=/srv/corekeeper` and `required_mountpoint=/`. If using a separate disk,
   require that disk's actual mountpoint instead. A normal `/srv/corekeeper`
   directory is not itself a mountpoint. This safeguard
   prevents starting maintenance on the system disk when the data disk is absent.
4. Enable the timer:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now corekeeper-update-check.timer
systemctl list-timers corekeeper-update-check.timer
journalctl -u corekeeper-update-check.service -n 30
```

## Backup and rollback policy

Maintenance gracefully stops the game, verifies a full archive of **all
`server-data` slots plus `server-files`**, then starts the candidate image and
updates the game when permitted. The binaries are included so a failed game
upgrade can really be rolled back. Caches/RootFS are excluded. Retention is one
or two archives (`backup_keep`); the example uses two. During an update a
temporary third archive can exist until the transaction finishes.

These are **update-triggered backups**, not daily save backups. If nothing
changes, no new archive is created. Copies on the same disk/VPS do not protect
against losing that disk or instance. Do not archive live saves and assume they
are consistent; this updater stops the game before backing up.

Failed startup/build certification restores the previous FEX container and the
pre-update game/save files. A host reboot/interruption leaves a transaction
journal and refuses further unattended maintenance until reviewed. Readiness is
not a client-connectivity or long-running-stability guarantee. If the installed
build is unknown, the first maintenance certifies it through a backed-up download
instead of pretending the latest public build is already installed.

Automatic rollback retains the original container during that transaction;
after successful certification it is removed. A later **manual** rollback is
separate: retain matching backups and a usable image reference. New
`update-state/previous.json` records include the local `image` ID and a
`repo_digests` list of registry pull references. The transaction journal also
records `previous_repo_digests` before stopping the game. A local image ID alone
cannot be used to pull a deleted image. Older records may lack registry digests,
local-only images can have an empty list, and registry retention is not guaranteed.

Maintenance preserves the container's `ACTIVATE_ALL_CONTENT` value (defaults to
`false` if absent). Updates do not silently opt an existing world into content
activation. Enable it yourself only after reviewing its irreversible effects.

Steam metadata failures fail closed without restarting. A manual
`sudo corekeeper-update-check --force` overrides the maintenance hour; use it
only when immediate downtime is intended. Do not run `apt upgrade` in the live
container; deploy a tested replacement image instead.


## Updating the updater itself

Image publication does not replace the host's separately installed updater or
readiness helper. For a helper upgrade, run **only the helper-install block in
step 2** outside an active transaction, followed by `sudo systemctl daemon-reload`
if the unit files changed. Do not recreate the JSON, reset the timezone, or
re-enable/change game settings just to upgrade scripts. The next timer run uses
the installed helpers; no game restart is needed solely for this upgrade.

Configuration is private and root-owned. Review existing settings separately;
preserve them rather than copying the example over them on every upgrade.

Daily image builds and automated dependency PRs are described in
[repository maintenance](../fex/README.md#build-and-dependency-policy). Host diagnostics
have their own [optional installer](../ops/diagnostics/README.md).

See [troubleshooting](troubleshooting.md) for timer errors, unknown builds,
interrupted transactions and manual rollback review. `--force` is an immediate
maintenance action, not a read-only diagnostic check.
