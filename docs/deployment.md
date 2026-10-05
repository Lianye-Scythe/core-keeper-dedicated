# Deployment guide

For a new server, follow the [Compose quick start](../README.md#quick-start).
This guide covers storage choices and alternative deployment methods.

## Requirements and storage

Use ARM64 Linux with rootful Docker. AMD64 images are not built by this fork;
rootless Docker is not part of the validated deployment. The Compose example
requires Compose **2.24.0 or newer** for optional `env_file` entries
([Docker documentation](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/)).

The public example uses these five bind mounts:

| Host path | Container path | Contents |
| --- | --- | --- |
| `/srv/corekeeper/server-data` | `/home/steam/core-keeper-data` | Worlds and persistent game/server configuration |
| `/srv/corekeeper/server-files` | `/home/steam/core-keeper-dedicated` | Installed game binaries, logs, `GameID.txt` and `GameInfo.txt` |
| `/srv/corekeeper/fex-cache` | `/home/steam/.cache/fex` | FEX cache location; does not itself enable disk caching |
| `/srv/corekeeper/mesa-cache` | `/home/steam/.cache/mesa_shader_cache` | Mesa shader cache |
| `/srv/corekeeper/update-control` | `/run/corekeeper-update` | Host updater's temporary update permit |

To use another disk, first mount it persistently, then change all five `source`
paths in the Compose file and create the directories there. Match the updater's
paths to the deployment. A directory named `/data` is not necessarily a mounted
filesystem; the host updater can explicitly require the real mount point.

Set positive numeric `PUID` and `PGID` values matching the intended file owner.
The entrypoint starts as root to prepare ownership and then drops privileges;
do not bypass this by adding Compose `user:`. `REPAIR_PERMISSIONS=true` is an
optional one-off recursive repair, not a setting needed for every startup.

Never give two running containers the same writable save directories. Keep saves
separate from caches, and do not delete data directories when removing a container.

## Plain Docker alternative

For a new installation without Compose:

```sh
sudo mkdir -p /srv/corekeeper/{server-data,server-files,fex-cache,mesa-cache,update-control}
docker run -d --name core-keeper-dedicated --restart unless-stopped \
  --stop-timeout 120 \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  -e PUID=1000 -e PGID=1000 -e WORLD_NAME='Core Keeper Server' \
  -e ACTIVATE_ALL_CONTENT=false \
  --mount type=bind,source=/srv/corekeeper/server-data,target=/home/steam/core-keeper-data \
  --mount type=bind,source=/srv/corekeeper/server-files,target=/home/steam/core-keeper-dedicated \
  --mount type=bind,source=/srv/corekeeper/fex-cache,target=/home/steam/.cache/fex \
  --mount type=bind,source=/srv/corekeeper/mesa-cache,target=/home/steam/.cache/mesa_shader_cache \
  --mount type=bind,source=/srv/corekeeper/update-control,target=/run/corekeeper-update \
  ghcr.io/lianye-scythe/core-keeper-dedicated:fex
```

Replace `1000` with your intended owner's IDs. Use `sudo` for Docker if needed.
Omitting `GAME_ID` generates one. Startup downloads use anonymous Steam access;
players need a legitimate compatible game client. Initial downloads and world
creation can take several minutes.

> [!WARNING]
> Content activation is disabled by default. Back up existing worlds before
> enabling `ACTIVATE_ALL_CONTENT=true`; it can permanently change them.

## Direct connections

The default Steam join-ID mode does not need a published game port. For direct
IP-based joining, set `SERVER_PORT=7778` in `core.env` and, if desired,
`PASSWORD`. Add this to the Compose service:

```yaml
ports:
  - "7778:7778/udp"
```

Match both ports to your selected `SERVER_PORT`. Compose does not use a service's
`core.env` file for `${SERVER_PORT}` interpolation; use a literal mapping as above,
or explicitly supply a Compose interpolation variable separately.

Allow the UDP port through the host firewall and cloud security rules; configure
router forwarding if applicable. Recreate the container with `docker compose up -d`.
Leave `SERVER_IP` empty unless a specific local bind address is needed: a cloud
public IP usually is not an address assigned inside the container.
Use the installed game's `README` and `ARGUMENTS` for the current client connection
syntax. Protect passwords and private `GameInfo.txt` contents when sharing diagnostics.

## Container lifecycle

Run Compose commands from `docker-compose-example`:

- `docker compose up -d`: create or recreate with changed configuration.
- `docker compose restart`: restart with the existing configuration; does not reload `core.env`.
- `docker compose down`: stop and remove the container/network; bind-mounted files remain.

Allow graceful shutdown before copying saves or replacing a container. Do not
run independent update mechanisms against the same game installation.

## Configured host bootstrap

[`fex/run-production.sh`](../fex/run-production.sh) is an optional bootstrap for
prepared host installation. It reads the same root-owned
`/etc/corekeeper-update-check.json` used by maintenance and diagnostics.
See [host configuration](../ops/diagnostics/README.md#shared-host-configuration).
By default it reads `/etc/corekeeper.env` and `<base>/ops/fex-image-ref`;
both must be root-owned regular files with mode `0600`. The image reference must
be an already-pulled ARM64 FEX digest, not a mutable tag.

Prepare all five data directories first. The script refuses to replace an
existing container and never resets saves. Owner IDs, content activation and
update gating come from the game environment file/image defaults, not hardcoded
host choices. No memory cap or kernel-core ulimit is imposed unless explicitly
requested in host configuration. This wrapper is optional; Compose remains the
recommended general setup.

Next: [configuration](configuration.md), [scheduled updates](maintenance.md), or
[troubleshooting](troubleshooting.md).
