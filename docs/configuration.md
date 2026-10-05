# Configuration

Set these environment variables in Compose or an optional `core.env`. Existing
configuration/world files are persistent in `server-data`.

## Defaults and precedence

The table below describes **image defaults**, not every deployment example. The
Compose example explicitly enables `ACTIVATE_ALL_CONTENT=true` and sets the tested
FEX runtime values. Its `environment:` entries override the same names in
`core.env`; edit those entries in Compose when overriding them. Other variables,
such as `GAME_ID`, `WORLD_INDEX` and `UPDATE_GATE_ENABLED`, can be set in `core.env`.
Never commit your private environment file.

After changing settings, recreate with `docker compose up -d` during planned
downtime; `docker restart` does not reload environment variables. Bind-mounted
saves persist. Settings are not all retroactive: seeds apply to new worlds,
changing the index selects another slot, and content activation cannot be undone.

> [!WARNING]
> Back up an existing world before content activation, importing saves or changing
> game versions. A new seed does not reset an existing slot.

## Environment reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `PUID`, `PGID` | `1000` | Positive host owner IDs; do not run the game as root. |
| `REPAIR_PERMISSIONS` | `false` | One-time repair after importing files; otherwise ownership markers avoid rescans. |
| `WORLD_INDEX` | `0` | World slot; changing it selects/creates another save, not another game version. |
| `WORLD_NAME` | `Core Keeper Server` | Displayed world/server name. |
| `WORLD_SEED`, `HASHED_WORLD_SEED` | empty | New-world seeds; empty means random, not a reset of an existing world. |
| `WORLD_MODE` | `0` | Normal `0`, Hard `1`, Creative `2`, Casual `4`. |
| `GAME_ID` | empty | Persistent join ID; 15–28 alphanumeric characters, excluding `Y`, `y`, `x`, `0`, `O`; invalid IDs may be replaced by the game. |
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
[the log parser](../scripts/logfile-parser.sh).

For mod.io, set `MODS_ENABLED=true`, `MODIO_API_KEY`, `MODIO_API_URL`, and
`MODS=mod-id[:version],other-mod`. Install required mod dependencies explicitly;
client-only mods can prevent a dedicated server from starting. Mod downloads on
startup are independent of the game/image maintenance gate; leave mods disabled
if all changes must be confined to the maintenance window.


## More detail

For version-specific argument values, consult the installed server's `README.txt`
and `ARGUMENTS.txt`. Do not publish `GameInfo.txt`: direct-mode connection details
can include a password. Private Docker inspections and rendered Compose output
can also expose credentials.

See [deployment](deployment.md), [scheduled maintenance](maintenance.md) and
[troubleshooting](troubleshooting.md). Low-level FEX/cache decisions are in the
[runtime notes](../fex/README.md).
