# Core Keeper Dedicated Server · FEX ARM64

Run a Core Keeper dedicated server on ARM64 Linux, including Oracle Cloud Ampere A1,
using Docker and FEX to execute the x86-64 game.

[![Build](https://github.com/Lianye-Scythe/core-keeper-dedicated-fex/actions/workflows/docker-image.yml/badge.svg?branch=main)](https://github.com/Lianye-Scythe/core-keeper-dedicated-fex/actions/workflows/docker-image.yml)

[Get started](#quick-start) · [Configuration](docs/configuration.md) ·
[Updates & backups](docs/maintenance.md) · [Troubleshooting](docs/troubleshooting.md)

## What this project provides

| Feature | Included / supported |
| --- | --- |
| Runtime | FEX on ARM64 Linux; validated on Oracle Cloud Ampere A1 |
| Deployment | Docker Compose with persistent saves, game files and cache directories |
| Game installation | Anonymous Steam downloads through native ARM64 DepotDownloader |
| Startup updates | Check and download game updates when the container starts |
| Scheduled maintenance | Optional host updater: hourly checks, a configurable update window, backups and rollback |
| Diagnostics | Optional host collectors with bounded retention |

No privileged container or host emulator registration is needed. Players still
need a legitimate, compatible Core Keeper client. This fork does not build AMD64
or Box64 images; see the [original project](https://github.com/escapingnetwork/core-keeper-dedicated)
for its supported variants.

> [!NOTE]
> This is an unofficial community project. CI checks packaging and startup;
> it cannot guarantee long-session stability or performance on every ARM64 host.

> [!IMPORTANT]
> Migrating from the original Box64 deployment? This fork's `latest` tag now
> means FEX on ARM64. Read the [migration guide](docs/migration.md) before replacing
> your existing container.

## Quick start

For a new server, use an ARM64 Linux host with rootful Docker and a recent Docker
Compose plugin **2.24.0 or newer** supporting optional `env_file` entries. These steps use
`/srv/corekeeper` and check for game updates at startup. For another disk,
existing saves or plain Docker, see [deployment options](docs/deployment.md).

### 1. Get the example and configure it

```sh
git clone https://github.com/Lianye-Scythe/core-keeper-dedicated-fex.git
cd core-keeper-dedicated-fex/docker-compose-example
cp core.env.example core.env
chmod 600 core.env
id -u
id -g
```

Edit `core.env`: set `PUID` and `PGID` to the positive numeric IDs printed above,
and choose `WORLD_NAME`. Leave `GAME_ID` empty to generate a join ID.
Use `sudo` for Docker commands below if your account needs it.

### 2. Create the data directories and start

```sh
sudo mkdir -p /srv/corekeeper/{server-data,server-files,fex-cache,mesa-cache,update-control}
docker compose config --quiet
docker compose up -d
```

The entrypoint prepares directory ownership, then runs the game as an
unprivileged user. The first start downloads the game and creates a world;
allow several minutes and watch the logs instead of repeatedly restarting.

> [!WARNING]
> Content activation is opt-in (`ACTIVATE_ALL_CONTENT=false`). Before enabling
> it for an existing world, back it up: content activation can
> permanently change that world. Never share writable saves between running containers.

### 3. Find your join ID

```sh
docker logs --tail 100 core-keeper-dedicated
docker exec core-keeper-dedicated cat /home/steam/core-keeper-dedicated/GameID.txt
```

Join through the game's multiplayer menu once the server has finished
initializing. A generated ID alone is not proof that the server is ready.
The default join-ID mode needs outbound Steam connectivity; publishing a game
port is unnecessary for this mode. For IP-based joining, see
[direct connections](docs/deployment.md#direct-connections).

## Common settings

Edit `docker-compose-example/core.env`, then run `docker compose up -d` from
that directory to recreate the container when its configuration changes.
`docker compose restart` does not reload environment settings.

| Setting | Example default | Purpose |
| --- | --- | --- |
| `PUID` / `PGID` | `1000` / `1000` | Host ownership for game files and saves |
| `WORLD_NAME` | `Core Keeper Server` | Server/world display name |
| `WORLD_INDEX` | `0` | Save slot; switching slots does not change the game version |
| `GAME_ID` | Empty | Generate a join ID, or set a valid custom one |
| `MAX_PLAYERS` | `8` | Player limit |

See [all configuration options](docs/configuration.md) for seeds, world modes,
content activation, direct connections, mods, Discord and runtime/cache settings.
Values explicitly set under Compose `environment` take precedence over `core.env`.

## Updates and data safety

By default, game updates are checked **at container startup**. Pulling a new image
does not replace a running container. There is no automatic timer or save backup
until you install and configure the optional host tools.

The [scheduled updater](docs/maintenance.md) can check hourly and apply changes
only during a chosen window. Its example uses **04:00 UTC** and retains
**two backups**. It compares game and image contents, stops the server for a
consistent backup, verifies the new startup and attempts rollback if it fails.
An unchanged server is not restarted.

> [!IMPORTANT]
> Enable the update gate only after configuring the host updater. Its backups
> include all save slots and installed game files, but are made only when applying
> updates—not daily or off-site. Host updater and diagnostic scripts are maintained
> separately from the container image.

## Documentation

| Guide | Contents |
| --- | --- |
| [Deployment](docs/deployment.md) | Storage, ownership, plain Docker, direct connections and lifecycle |
| [Configuration](docs/configuration.md) | Complete settings, defaults and precedence |
| [Scheduled maintenance](docs/maintenance.md) | Updates, backup retention, rollback and host script upgrades |
| [Troubleshooting](docs/troubleshooting.md) | Startup failures, connection issues and safe checks |
| [Host diagnostics](ops/diagnostics/README.md) | Optional crash/network collection, retention and privacy |
| [Runtime and build policy](fex/README.md) | FEX settings, caches, Ubuntu environments, tags and dependencies |
| [Migration](docs/migration.md) | Moving from Box64 or older image/repository names |

## Attribution and license

Derived from [escapingnetwork/core-keeper-dedicated](https://github.com/escapingnetwork/core-keeper-dedicated),
with thanks to its contributors. This fork is maintained by
[Lianye-Scythe](https://github.com/Lianye-Scythe) and retains the original history
and attribution. Repository code is licensed under [MIT](LICENSE).

Not affiliated with Pugstorm or FEX. The game and bundled third-party components
remain subject to their respective licenses.
