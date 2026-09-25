# Core Keeper Dedicated Server

![corekeeper](https://user-images.githubusercontent.com/136487/168213246-7f561105-136e-47fa-abd9-fac1c97ca48d.png)

Explore an endless cavern of creatures, relics and resources in a mining sandbox adventure for 1-8 players. Mine, build, fight, craft and farm to unravel the mystery of the ancient Core. [Get Core Keeper at the Steam Store](https://store.steampowered.com/app/1621690/Core_Keeper/)

[![Docker image](https://github.com/Lianye-Scythe/core-keeper-dedicated/actions/workflows/docker-image.yml/badge.svg?branch=main)](https://github.com/Lianye-Scythe/core-keeper-dedicated/actions/workflows/docker-image.yml)

## Supported tags and respective `Dockerfile` links
- [`ghcr.io/lianye-scythe/core-keeper-dedicated:latest` (*Dockerfile*)](./Dockerfile)

The fork publishes multi-platform images to GHCR on pushes to `main` and daily rebuilds. The image uses Debian 12 Bookworm to prioritize the supported LTS line over a major-version switch; each image build refreshes APT metadata and installs available Bookworm package upgrades. After the first successful publish, set the GHCR package visibility to **Public** if the VPS should pull it without registry credentials; otherwise authenticate Docker on the VPS with a GitHub token that can read packages.

## Automated maintenance

Dependabot checks Docker and GitHub Actions dependencies daily. Patch and minor updates are queued for auto-merge only after the required multi-platform build and shell checks pass; major-version updates remain open for manual review. The `main` branch requires pull requests and both checks. VPS deployments can poll the published image and apply content changes during a local maintenance window; rebuild-time metadata changes alone should not require a restart.

## How to run

### ARM based configuration

This image currently includes the following Box64 build variants for the following devices:

- Generic [generic]
- Raspberry Pi 3 [rpi3]
- Raspberry Pi 4 [rpi4-pre3]
- Raspberry Pi 5 (4K page size) [rpi5]
- Raspberry Pi 5 (16K page size) [rpi5_16k]
- M1 (M-Series) Mac [m1]
- ADLink Ampere Altra (Oracle ARM CPUs) [adlink]

By default it is set to use `generic`. If you want to use another one, change the enviromental variable `ARM64_DEVICE` at the `core.env` file.

Oracle Cloud A1 uses Ampere Altra CPUs, for which the image also provides the `adlink` Box64 variant. `generic` remains the conservative default; compare stability and performance on your workload before switching variants.

### Volumes

Create two directories where you want to run your server :

- `server-data`: mandatory if you want to keep configuration between each restart
- `server-files`: optional, contains all the files of the application

Then modify `/host/path/to/server-data` and/or `/host/path/to/server-files` in one of the examples below to match the paths of the folders you created.

### Using Docker CLI:

```bash
docker run -d \
  --name core-keeper-dedicated \
  -e WORLD_NAME="Core Keeper Server" \
  -e MAX_PLAYERS=5 \
  -v /host/path/to/server-data:/home/steam/core-keeper-data \
  -v /host/path/to/server-files:/home/steam/core-keeper-dedicated \
  ghcr.io/lianye-scythe/core-keeper-dedicated:latest
```

### Using Docker Compose
Create a [`docker-compose.yml`](./docker-compose-example/docker-compose.yml) with the following content:

```yml
services:
  core-keeper:
    image: ghcr.io/lianye-scythe/core-keeper-dedicated:latest
    container_name: core-keeper-dedicated
    restart: unless-stopped
    stop_grace_period: 2m
    # Port is only needed if using direct connection mode
    # ports:
    #   - "$SERVER_PORT:$SERVER_PORT/udp"
    volumes:
      - /host/path/to/server-files:/home/steam/core-keeper-dedicated
      - /host/path/to/server-data:/home/steam/core-keeper-data
    env_file:
      - path: core.env
        required: false
```

Create a `core.env` file and override the desired environmental variables for the dedicated server, see configuration for reference. Example:
```env
ARM64_DEVICE=rpi5
MAX_PLAYERS=3
```

On the folder which contains the files run `docker compose up -d`.

A `GameID.txt` file will be created next to the executable containing the Game ID. If it doesn't appear you can check the docker logs (`docker logs core-keeper-dedicated` or `docker compose logs`) for errors.

To query the game ID run:
`docker exec -it core-keeper-dedicated cat /home/steam/core-keeper-dedicated/GameID.txt`

## Configuration

These are the arguments you can use to customize server behavior with default values.

| Argument | Default | Description |
| :---:   | :---: | :---: |
| PUID | 1000 | The user ID on the host that the container should use for file ownership and permissions. |
| PGID | 1000 | The group ID on the host that the container should use for file ownership and permissions. |
| ARM64_DEVICE | generic | The Box64 build variants. Accepts `generic`, `rpi3`, `rpi4-pre3`, `rpi5`, `rpi5_16k`, `m1` and `adlink`. |
| USE_DEPOT_DOWNLOADER | true | Use the native DepotDownloader build instead of SteamCMD. Recommended for ARM64 hosts. |
| WORLD_INDEX | 0 | Which world index to use. |
| WORLD_NAME | "Core Keeper Server" | The name to use for the server. |
| WORLD_SEED | "" | The seed to use for a new world. Set to "" to generate a random seed. |
| HASHED_WORLD_SEED | "" | The hashed seed to use for a new world, added in v1.1. Set to "" to generate a random seed. |
| WORLD_MODE | 0 | Sets the world mode for the world. Can be Normal (0), Hard (1), Creative (2), Casual (4). |
| GAME_ID | "" | Game ID to use for the server. Need to be at least 15 characters, no longer than 28 characters and alphanumeric. Empty or invalid means a new ID will be generated at start. |
| MAX_PLAYERS | 8 | Maximum number of players allowed to connect. |
| ACTIVATE_ALL_CONTENT | false | Enables all currently available content bundles for an existing world. Content activation changes the world and cannot be undone; back up the world first. |
| UPDATE_GATE_ENABLED | false | When true, only downloads server updates when a fresh permit file exists (except the first install). Use with the scheduled-update example below. |
| UPDATE_PERMIT_FILE | `/run/corekeeper-update/apply-update` | Path to the host-issued update permit inside the container. |
| UPDATE_PERMIT_MAX_AGE_SECONDS | 3600 | Maximum age of an update permit before it is ignored. |
| SEASON | No Default | Overrides current season by setting to any of None (0), Easter (1), Halloween (2), Christmas (3), Valentine (4), Anniversary (5), CherryBlossom (6), LunarNewYear(7).<br/>**Do not set this env var if you want real date season.** |
| SERVER_IP | No Default | Only used if port is set. Sets the address that the server will bind to. Supports ipv4 and ipv6 addresses. If not set, default value 0.0.0.0 is used, which will accept connections from any internal ip. |
| SERVER_PORT | No Default | Port used for direct connection mode. **Setting an value to this will cause the server behaviour to change!** [See Network Mode](#network-mode) |
| PASSWORD | No Default | Password players should use when trying to join using direct connections. Maximum length password can be 28 characters. If omitted or invalid, a random password will be generated.|
| ACTIVATE_CONTENT | "" | Comma separated list to turn on biomes for worlds created prior to v1.1. Valid values are `GiantCicadaBossDungeon`, `NatureBiomeCicadas`, `GuaranteedOases`, `BiomeStatues`, and `AbioticFactor`. Once enabled, they cannot be disabled! |
| ALLOW_ONLY_PLATFORM | No Default | Allow only players from given platform. If not set all platforms are allowed. Has no effect unless -port is also set enabling Direct Connections. Can be Steam (1), Epic (2), Microsoft (3), GOG (4). |
| DISCORD_WEBHOOK_URL | "" | Webhook url (Edit channel > Integrations > Create Webhook). |
| DISCORD_PLAYER_JOIN_ENABLED | true | Enable/Disable message on player join |
| DISCORD_PLAYER_JOIN_MESSAGE | `"$${char_name} ($${steamid}) has joined the server."` | Embed message |
| DISCORD_PLAYER_JOIN_TITLE | "Player Joined" | Embed title |
| DISCORD_PLAYER_JOIN_COLOR | "47456" | Embed color |
| DISCORD_PLAYER_LEAVE_ENABLED | true | Enable/Disable message on player leave |
| DISCORD_PLAYER_LEAVE_MESSAGE | `"$${char_name} ($${steamid}) has disconnected. Reason: $${reason}."` | Embed message |
| DISCORD_PLAYER_LEAVE_TITLE | "Player Left" | Embed title |
| DISCORD_PLAYER_LEAVE_COLOR | "11477760" | Embed color |
| DISCORD_SERVER_START_ENABLED | true | Enable/Disable message on server start |
| DISCORD_SERVER_START_MESSAGE | `"**World:** $${world_name}\n**GameID:** $${gameid}"` | Embed message. Available variables are `world_name`, `gameid`, (the following only in direct connection mode) `allowed_platforms`, `public_ip`, `port`, `password`, `join_string`|
| DISCORD_SERVER_START_TITLE | "Server Started" | Embed title |
| DISCORD_SERVER_START_COLOR | "2013440" | Embed color |
| DISCORD_SERVER_STOP_ENABLED | true | Enable/Disable message on server stop |
| DISCORD_SERVER_STOP_MESSAGE | "" | Embed message |
| DISCORD_SERVER_STOP_TITLE | "Server Stopped" | Embed title |
| DISCORD_SERVER_STOP_COLOR | "12779520" | Embed color |
| MODS_ENABLED | false | Enable/Disable mod support |
| MODIO_API_KEY | "" | mod.io API key |
| MODIO_API_URL | "" | mod.io API path |
| MODS | "" | List of mods to install |

## Scheduled update checks (optional)

By default, the container checks Steam for updates each time it starts, matching the original behavior. To let a host timer check for updates and only restart the server during a maintenance window, enable the update gate and install the example systemd timer. The example below checks hourly and applies a detected public build at **17:00 Asia/Taipei**. It backs up the entire `server-data` directory (all world slots and server data) before updating and retains only the newest one or two backups.

In `core.env`, set:

```env
UPDATE_GATE_ENABLED=true
UPDATE_PERMIT_FILE=/run/corekeeper-update/apply-update
UPDATE_PERMIT_MAX_AGE_SECONDS=3600
```

Add this bind mount to the Compose service and create the matching host directory. The directory must be writable by the container's configured `PUID`/`PGID`, because the container removes a consumed permit:

```yaml
volumes:
  - /host/path/to/update-control:/run/corekeeper-update:rw
```

For example, if `PUID=1000` and `PGID=1000`, create it with `sudo install -d -o 1000 -g 1000 -m 0775 /host/path/to/update-control`.

Then install the example checker and systemd units from `examples/scheduled-updates/`. Copy `corekeeper-update-check.conf.example` to `/etc/corekeeper-update-check.conf`, edit its host paths and container name, and make sure its `UPDATE_BUILD_ID_FILE`, `UPDATE_PERMIT_FILE`, and `CONTAINER_PERMIT_PATH` correspond to the Compose settings above. `UPDATE_BUILD_ID_FILE` is maintained by the host checker only after the server starts successfully. From the repository root, install the files with:

The host needs systemd, rootful Docker, `curl`, `jq`, `tar`, and `flock` (from `util-linux`). On Debian/Ubuntu, install the missing utilities with `sudo apt-get install curl jq tar util-linux`.

```sh
sudo install -o root -g root -m 0755 examples/scheduled-updates/corekeeper-update-check /usr/local/sbin/corekeeper-update-check
sudo install -o root -g root -m 0644 examples/scheduled-updates/corekeeper-update-check.service /etc/systemd/system/
sudo install -o root -g root -m 0644 examples/scheduled-updates/corekeeper-update-check.timer /etc/systemd/system/
sudo install -o root -g root -m 0600 examples/scheduled-updates/corekeeper-update-check.conf.example /etc/corekeeper-update-check.conf
```

Edit `/etc/corekeeper-update-check.conf` to match the real host paths before enabling it, then run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now corekeeper-update-check.timer
systemctl list-timers corekeeper-update-check.timer
```

The first gated install still downloads the server files. If an existing server has no recorded build ID yet, its first scheduled check treats the version as unknown and queues one backup/update/restart at the next maintenance window. The checker reads the public build ID from `api.steamcmd.net`; if that metadata service is unavailable or returns an unexpected response, it fails closed and does not restart the server. This automates the dedicated-server files only; it does not update the Docker image itself.

If a backup cannot be created or verified, the checker deliberately leaves the container stopped and does not issue an update permit. Resolve the disk/permission problem, then start the container manually; the next hourly check can safely resume the update workflow.
## Mod Support

The container supports automatically installing mods from [mod.io](https://mod.io/g/corekeeper).

1. Get a mod.io API key from [mod.io/me/access](https://mod.io/me/access)
    - You'll need the API path that is generated along with the key (e.g. https://u-*.modapi.io/v1)
2. Set the necessary environment variables in your `core.env` file (or in your `docker-compose.yml`)
  - `MODS_ENABLED=true`
  - `MODIO_API_KEY=your_api_key`
  - `MODIO_API_URL=your_api_url`
  - `MODS=mod1,mod2` (see below)

### Specify mods to install

> [!WARNING]
> Installing a client-only mod can cause the server to not start. Don't install client-only mods (they wouldn't do anything on the server anyway).

> [!IMPORTANT]
> Mod dependencies are not automatically installed. You must look at the dependencies for each mod you want to install and add their dependencies to the list.

You'll need to get the mod string ID from mod.io for each mod you want to install. The easiest way to do this is to grab it from the URL.

For example, looking at the URL for [CoreLib](https://mod.io/g/corekeeper/m/core-lib) (`https://mod.io/g/corekeeper/m/core-lib`), you would use `core-lib`.

Specify mods as a comma-separated list, optionally providing a version:

```sh
# Format: <mod_id>[:<version>], ...
MODS=core-lib,coreliblocalization,corelibrewiredextension,ck-qol
```

Example using specific versions:

```sh
MODS=core-lib,coreliblocalization,corelibrewiredextension:3.0.1,ck-qol:1.9.4
```

- If `version` is not specified, the latest version will be installed.
- Mods are reinstalled whenever the container is started, so to update mods to their latest version, simply restart the container.

## Network Mode

Currently Core Keeper supports two network modes: SDR (Steam Datagram Relay) and Direct Connect.

### SDR (Steam Datagram Relay)
In this mode, the server uses [Valve's Virtual Network](https://partner.steamgames.com/doc/features/multiplayer/steamdatagramrelay) to route traffic through Steam's relay infrastructure. Instead of players connecting directly to the server's IP address, all communication goes through secure relay nodes managed by Steam. This hides the server’s real IP, protects against DDoS attacks, and improves NAT traversal.

Because of this relay system, server operators do not need to open any ports on their router or firewall—as long as outbound connections to Steam are allowed, the server can communicate with clients reliably.

### Direct Connection
In Direct Connect mode, players connect straight to the server’s public IP address without going through Steam's relay network. This can result in lower latency and more direct communication, but it requires the server to be reachable from the internet.

Server operators must open and forward the necessary ports on their router or firewall to allow incoming connections. Unlike SDR, this mode exposes the server’s IP address to clients and may be more vulnerable to connection issues or attacks.

> [!IMPORTANT]<br>
> The SERVER_PORT environment variable determines the server's network mode.<br>
> Leave it empty to use SDR (no port forwarding needed).<br>
> Setting a value switches to Direct Connect, which requires opening and forwarding ports.<br>
> Only set this if you specifically want Direct Connect.

### Contributors
<a href="https://github.com/escapingnetwork/core-keeper-dedicated/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=escapingnetwork/core-keeper-dedicated" />
</a>

Made with [contrib.rocks](https://contrib.rocks).
