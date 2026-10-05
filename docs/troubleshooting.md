# Troubleshooting and maintenance boundaries

Never delete `server-data` or choose a new `WORLD_INDEX` as a connection fix.
Never share writable saves with a second running container. First preserve the
incident time, client/server versions, and logs. Diagnostics may contain private
join IDs, passwords, webhook tokens and other container environment values.

## First checks

```sh
docker inspect --format '{{json .State}}' core-keeper-dedicated
docker logs --timestamps --tail 200 core-keeper-dedicated
```

Use `sudo` if your host account does not have Docker access. Do not run
`docker compose config` without `--quiet` when sharing output: rendered environment
values can include credentials. Do not publish a full `docker inspect` dump.

## Slow initialization / Game ID exists but clients cannot join

FEX startup and first-world generation on A1 can take several minutes. Historical
isolated runs took about four minutes with bounded-16 translation; that is not a
startup deadline for every game version, world or host load. A busy CPU by itself
does not prove a hang. `GameID.txt` can exist before the world is ready.

If the host readiness helper is installed:

```sh
sudo /usr/local/libexec/corekeeper-ready core-keeper-dedicated
```

Exit 0 means current-boot Steam session, world and simulation markers were found;
nonzero means startup is not confirmed. The helper does not test a real client
connection or continuously detect hangs, and old startup markers can outlive a
later failure. Do not repeatedly restart a server that is still initializing.
If progress stops, collect evidence before restarting; there is no proven universal
time limit or reliable hang test based only on CPU usage.

## Closed connection / game not found

Check whether the container exited, restarted, or was in the update window. Read
logs for the **current boot**, rather than assuming an old ready message applies.
Confirm the client is on the same game release/branch and that the join ID matches:

```sh
docker exec core-keeper-dedicated cat /home/steam/core-keeper-dedicated/GameID.txt
```

Steam-ID mode depends on outbound Steam connectivity; opening a random inbound
UDP port will not repair it. Direct connection mode is a separate configuration.
Network evidence can distinguish an observed Steam-session interruption from a
container exit, but passing HTTP/TCP probes does not prove Steam relay/UDP health.
Do not conclude that every disconnect is a FEX bug.

## Updates do not happen / scheduled maintenance failed

```sh
systemctl list-timers corekeeper-update-check.timer
sudo journalctl -u corekeeper-update-check.service -n 100 --no-pager
```

- Default deployment checks game downloads at startup; no host timer is installed
  automatically. Gated deployment requires the installed/enabled host timer.
- A changed image/game is queued until the configured local maintenance hour
  (04:00 UTC in the public example); an unchanged build does not cause a restart.
- Steam build metadata currently uses `api.steamcmd.net`, a third-party service.
  Metadata failure, unavailable registry, missing data mount or unsupported
  container configuration fails closed, leaving the server alone if maintenance
  has not started. A later timer run retries; repeated failures need review.
- A stopped server is not automatically started by the updater; it does not
  override an intentional stop.
- A transaction interrupted by a host reboot or process termination requires
  manual review. Do not delete `update-state/transaction.json` merely to silence
  the error, and do not run a second updater against the same saves.

`sudo corekeeper-update-check --force` bypasses the hour, not the safety checks.
It may stop the game immediately; it is not a harmless diagnostic command.
An image update does not install newer host-side helpers: review and reinstall
those from the repository separately, outside maintenance.

## Rollback and backup review

A failed candidate startup/build certification triggers automatic rollback to
the previous container and pre-update files. Successful updates do not promise
compatibility with every client/mod, so later-discovered failures need a manual
rollback plan. Inspect private `update-state/previous.json`, any unfinished
transaction, available images and backup archives before acting. Paths below use
the public example layout; adapt them to your configured base directory:

```sh
sudo ls -lh /srv/corekeeper/backups
sudo ls -l /srv/corekeeper/update-state
docker image ls --digests
```

For a selected archive, check `gzip -t` and `tar -tzf` before any recovery. Listing
an archive is not permission to extract it over a running world. Restoration
requires the game stopped, an appropriate game image/binaries, and reviewed paths;
never blindly use an old join ID or reset a save slot to hide a failed restore.
Deleted images may need pulling again by their recorded immutable digest.

Archives contain **all world slots plus game binaries**, not just the selected
slot. They exclude caches and the container RootFS. Only actual maintenance makes
a new backup; the one/two-archive policy is not a daily backup schedule or offsite
disaster recovery.

## World slots and applying settings

`WORLD_INDEX=0`, `1`, etc. select different saves in the same installed game
version. Reusing an existing slot loads it; an unused slot creates a world.
Changing seed/name variables is not a guaranteed reset of an existing world.
Content activation can change existing saves irreversibly; back up first.

Changing Compose/environment files requires container recreation to apply;
`docker restart` preserves the old container environment. Do not run the managed
bootstrap against an existing container. Coordinate configuration changes with
maintenance; do not run competing image updaters/Watchtower for this deployment.

## Disk usage and diagnostic limits

```sh
df -h /srv/corekeeper
docker system df
sudo journalctl -u corekeeper-diagnostics-retention.service -n 30 --no-pager
```

Only the optional diagnostic installer enables host log/evidence retention. Docker
log rotation in the examples is separate from game log files. Retention protects
open/recent files and the newest evidence; its size targets are **not hard disk
quotas**. Warnings about protected data require inspection, not truncating active
logs. Never use a global Docker prune to clean this one service on a shared VPS.
See [diagnostic limits and removal](../ops/diagnostics/README.md) for details.
