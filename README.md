# Core Keeper Dedicated Server — FEX ARM64

Unofficial Docker server for **ARM64 Linux**, including Oracle Cloud Ampere A1.
The native ARM64 container runs the x86-64 game through [FEX](https://fex-emu.com/).
This project is independently maintained as a fork of
[escapingnetwork/core-keeper-dedicated](https://github.com/escapingnetwork/core-keeper-dedicated).
It is not affiliated with the game developer or FEX maintainers.

[![FEX image](https://github.com/Lianye-Scythe/core-keeper-dedicated-fex/actions/workflows/docker-image.yml/badge.svg?branch=main)](https://github.com/Lianye-Scythe/core-keeper-dedicated-fex/actions/workflows/docker-image.yml)

## Migration notice

This repository now supports **FEX/ARM64 only**. Box64 build variants and AMD64
images are no longer built. For deployment continuity, the existing public package
`ghcr.io/lianye-scythe/core-keeper-dedicated` uses `fex` and `latest` for the
same tested ARM64 image. Its name intentionally remains unchanged when the GitHub
repository is renamed; **its `latest` tag changes from Box64 to FEX/ARM64**.
Existing users must review this architecture/runtime change before pulling.
Never share writable saves between servers.
Changing the image does not delete worlds or change a configured Game ID.

## Images and compatibility

- `ghcr.io/lianye-scythe/core-keeper-dedicated:fex`: recommended update channel.
- `:latest`: identical FEX/ARM64 channel, not the previous Box64 image.
- `:fex-<commit>`: source revision label, **not immutable** across daily rebuilds.
- `@sha256:<digest>`: immutable image reference for reproducibility/rollback.

The native ARM64 container uses **Ubuntu 26.04 LTS**; its extracted x86-64 guest
RootFS remains on **Ubuntu 24.04 LTS** from FEX's official manifest. The Docker
host may use a different distribution/version; the container shares its kernel.
FEX comes from
its official stable PPA; DepotDownloader uses its latest stable, non-prerelease
release during CI. Daily builds refresh APT/FEX and the official RootFS manifest.
RootFS XXH3-64 is verified; URL/hash/SHA-256 are recorded in
`/opt/fex-rootfs-source.json`. `/opt/depot-downloader-version` records the downloader.
An LTS release upgrade is deliberately reviewed rather than silently adopted.

The validated game-specific settings are `FEX_MULTIBLOCK=1`, `FEX_MAXINST=16`,
with normal SMC tracking (`FEX_SMCCHECKS=1`) and default memory ordering. The block
limit is a workaround, not an upstream default or proven optimum. Core Keeper
1.3.0.4 has passed startup and short multiplayer play on the managed A1 host;
**long-running stability is not yet established**. See [runtime notes](fex/README.md)
and [historical investigation](fex/RESULTS.md). CI smoke tests are not game tests.

No `--privileged`, host binfmt registration, FUSE mount or CPU affinity is needed.
Do not add `-nographics`: world generation needs the shipped graphical path.

## Quick start

Use an ARM64 host with rootful Docker. Create separate writable directories for
`server-data`, `server-files`, `fex-cache` and `mesa-cache`, then adapt the paths in
[the Compose example](docker-compose-example/docker-compose.yml).

```sh
docker run -d --name core-keeper-dedicated --restart unless-stopped \
  --stop-timeout 120 \
  -e PUID=1000 -e PGID=1000 -e WORLD_NAME='Core Keeper Server' \
  -e GAME_ID='YourOwnGameId123' -e ACTIVATE_ALL_CONTENT=true \
  --mount type=bind,src=/srv/corekeeper/server-data,dst=/home/steam/core-keeper-data \
  --mount type=bind,src=/srv/corekeeper/server-files,dst=/home/steam/core-keeper-dedicated \
  --mount type=bind,src=/srv/corekeeper/fex-cache,dst=/home/steam/.cache/fex \
  --mount type=bind,src=/srv/corekeeper/mesa-cache,dst=/home/steam/.cache/mesa_shader_cache \
  ghcr.io/lianye-scythe/core-keeper-dedicated:fex
```

This quick start checks/downloads game updates **on startup**. To update only in
a maintenance window, use the scheduled updater below instead. The first install
downloads the server anonymously; players still need a legitimate compatible
game client. Generation on A1 can take several minutes before clients can join.

```sh
docker logs --tail 100 core-keeper-dedicated
docker exec core-keeper-dedicated cat /home/steam/core-keeper-dedicated/GameID.txt
```

`GameID.txt` alone is not sufficient proof that world initialization is complete.
The updater additionally checks current-boot world/session/simulation log markers.
Steam Game ID mode needs outbound connectivity; no published game port is required.
Set `SERVER_PORT` and publish its UDP port only for direct connection mode.

## Server settings

Set these environment variables in Compose or an optional `core.env`. Existing
configuration/world files are persistent in `server-data`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PUID`, `PGID` | `1000` | Positive host owner IDs; do not run the game as root. |
| `REPAIR_PERMISSIONS` | `false` | One-time repair after importing files; otherwise ownership markers avoid rescans. |
| `WORLD_INDEX` | `0` | World slot; changing it selects/creates another save, not another game version. |
| `WORLD_NAME` | `Core Keeper Server` | Displayed world/server name. |
| `WORLD_SEED`, `HASHED_WORLD_SEED` | empty | New-world seeds; empty means random, not a reset of an existing world. |
| `WORLD_MODE` | `0` | Normal `0`, Hard `1`, Creative `2`, Casual `4`. |
| `GAME_ID` | empty | Persistent join ID; a valid ID is 15–28 alphanumeric characters. |
| `MAX_PLAYERS` | `8` | Player limit. |
| `ACTIVATE_ALL_CONTENT` | `false` | Activate available content for existing worlds; back up first, activation is not reversible. |
| `ACTIVATE_CONTENT` | empty | Specific comma-separated content bundle identifiers supported by the installed game. |
| `SEASON` | empty | Leave empty for real-date season; use the installed server's documented enum to override. |
| `SERVER_IP`, `SERVER_PORT` | empty | Direct connection address/UDP port; setting a port changes connection mode. |
| `PASSWORD` | empty | Direct-mode password, up to 28 characters; game may generate one when omitted/invalid. |
| `ALLOW_ONLY_PLATFORM` | empty | Direct-mode platform filter: Steam `1`, Epic `2`, Microsoft `3`, GOG `4`. |
| `UPDATE_GATE_ENABLED` | `false` | Require a fresh host permit for game updates, except initial installation. |
| `UPDATE_PERMIT_FILE` | `/run/corekeeper-update/apply-update` | Permit path inside the container. |
| `UPDATE_PERMIT_MAX_AGE_SECONDS` | `3600` | Reject stale permits. |
| `FEX_MULTIBLOCK`, `FEX_MAXINST` | `1`, `16` | Tested Core Keeper translation settings, not upstream defaults. |
| `FEX_APP_CACHE_LOCATION` | `/home/steam/.cache/fex/` | Persistent FEX cache location; does not enable otherwise-disabled disk caches. |
| `MESA_SHADER_CACHE_MAX_SIZE` | `512M` | Mesa driver cache budget, not a RAM reservation or FEX cache setting. |

`USE_DEPOT_DOWNLOADER=true` and `COREKEEPER_RUNTIME=fex` are the supported runtime;
do not select the removed Box64/SteamCMD path. See the installed game's server
README for version-specific flags/content identifiers rather than assuming a
historical list is exhaustive.

### Discord and mods

`DISCORD_WEBHOOK_URL` enables webhook delivery. Player join/leave and server
start/stop switches are `DISCORD_PLAYER_JOIN_ENABLED`,
`DISCORD_PLAYER_LEAVE_ENABLED`, `DISCORD_SERVER_START_ENABLED`, and
`DISCORD_SERVER_STOP_ENABLED` (default `false`). Each event also supports
`..._TITLE`, `..._MESSAGE`, and `..._COLOR` overrides; templates are implemented in
[the log parser](scripts/logfile-parser.sh).

For mod.io, set `MODS_ENABLED=true`, `MODIO_API_KEY`, `MODIO_API_URL`, and
`MODS=mod-id[:version],other-mod`. Install required mod dependencies explicitly;
client-only mods can prevent a dedicated server from starting. Mod downloads on
startup are independent of the game/image maintenance gate; leave mods disabled
if all changes must be confined to the maintenance window.

## Scheduled game and image updates

The [host updater](fex/update.py) checks hourly and applies detected changes at
**17:00 Asia/Taipei**. There is no restart when game build and image contents are
unchanged. Image comparison includes installed packages, scripts, downloader and
guest RootFS provenance; rebuild timestamps/labels alone are ignored.

The updater supports the documented rootful Docker deployment with default bridge
network and the five bind mounts. It preserves the Game ID, selected world, name,
user overrides, memory limits and published ports. Unsupported configurations are
rejected before stopping the server rather than silently discarded.

1. Set `UPDATE_GATE_ENABLED=true`, `ACTIVATE_ALL_CONTENT=true`, and bind a writable
   `update-control` directory to `/run/corekeeper-update`. Ensure its ownership
   matches `PUID`/`PGID`.
2. Install the helpers and root-owned JSON configuration:

```sh
sudo install -d /usr/local/libexec/corekeeper
sudo install -m 0755 fex/readiness.py /usr/local/libexec/corekeeper-ready
sudo install -m 0644 fex/update.py /usr/local/libexec/corekeeper/update.py
sudo install -m 0755 examples/scheduled-updates/corekeeper-update-check /usr/local/sbin/
sudo install -m 0644 examples/scheduled-updates/corekeeper-update-check.{service,timer} /etc/systemd/system/
sudo install -m 0600 examples/scheduled-updates/corekeeper-update-check.json.example /etc/corekeeper-update-check.json
```

3. Edit `/etc/corekeeper-update-check.json`: set the real base directory and the
   mounted filesystem it lives on (`required_mountpoint`, e.g. `/data`). It must
   already contain all four data/cache directories. Host dependencies are Python
   3.10+, Docker, GNU tar and systemd; the image has the download dependencies.
4. Enable the timer:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now corekeeper-update-check.timer
systemctl list-timers corekeeper-update-check.timer
journalctl -u corekeeper-update-check.service -n 30
```

Maintenance gracefully stops the game, verifies a full archive of **all
`server-data` slots plus `server-files`**, then starts the candidate image and
updates the game when permitted. The binaries are included so a failed game
upgrade can really be rolled back. Caches/RootFS are excluded. Retention is one
or two archives (`backup_keep`); the managed host uses two. During an update a
temporary third archive can exist until the transaction finishes.

Failed startup/build certification restores the previous FEX container and the
pre-update game/save files. A host reboot/interruption leaves a transaction
journal and refuses further unattended maintenance until reviewed. Readiness is
not a client-connectivity or long-running-stability guarantee. If the installed
build is unknown, the first maintenance certifies it through a backed-up download
instead of pretending the latest public build is already installed.

Steam metadata failures fail closed without restarting. A manual
`sudo corekeeper-update-check --force` overrides the maintenance hour; use it
only when immediate downtime is intended. Do not run `apt upgrade` in the live
container; deploy a tested replacement image instead.

## Repository maintenance

Daily CI checks the latest stable DepotDownloader, refreshes FEX/APT and official
RootFS, runs shell/unit checks and native ARM64 guest/ownership smoke tests, then
publishes **only from `main`**. PRs test without publishing. Dependabot checks
Docker/Actions daily; patch/minor updates use auto-merge after required checks.
Major/LTS changes stay under review. The GHCR package must be public for anonymous
VPS pulls, or Docker needs registry credentials.

## Attribution and license

Original Docker/server work: [escapingnetwork/core-keeper-dedicated](https://github.com/escapingnetwork/core-keeper-dedicated)
and its contributors. FEX adaptation, scheduled maintenance and ongoing project
maintenance: [Lianye-Scythe](https://github.com/Lianye-Scythe).
Git history and original copyright notices are retained; see [MIT LICENSE](LICENSE).
FEX, Ubuntu, DepotDownloader and Core Keeper retain their respective licenses.
