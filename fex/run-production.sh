#!/bin/bash
# Managed Oracle A1 FEX deployment; existing saves are never reset by this script.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
mountpoint -q /data || { echo '/data is not mounted.' >&2; exit 1; }
BASE=/data/corekeeper
read -r image < "$BASE/ops/fex-image-ref"
env_file=/etc/corekeeper-fex.env
[[ -f $env_file && ! -L $env_file && $(stat -c %u "$env_file") == 0 ]]
[[ $image == *@sha256:* ]] || { echo 'An immutable FEX image is required.' >&2; exit 1; }
docker image inspect "$image" >/dev/null
[[ $(docker image inspect -f '{{range .Config.Env}}{{if eq . "COREKEEPER_RUNTIME=fex"}}yes{{end}}{{end}}' "$image") == yes ]]
if docker inspect core-keeper-dedicated >/dev/null 2>&1; then
    echo 'Container already exists; restart it instead of recreating saves.' >&2
    exit 1
fi
for directory in server-data server-files fex-cache mesa-cache update-control; do
    [[ -d $BASE/$directory && ! -L $BASE/$directory ]]
done
[[ -x $BASE/server-files/CoreKeeperServer ]]
docker run -d --name core-keeper-dedicated --restart unless-stopped \
    --stop-timeout 120 --memory 10g --memory-swap 10g --ulimit core=-1 \
    --log-opt max-size=10m --log-opt max-file=3 \
    -e PUID=1001 -e PGID=1001 -e COREKEEPER_RUNTIME=fex \
    -e USE_DEPOT_DOWNLOADER=true -e UPDATE_GATE_ENABLED=true \
    -e FEX_MULTIBLOCK=1 -e FEX_MAXINST=16 -e FEX_SMCCHECKS=1 \
    -e FEX_APP_CACHE_LOCATION=/home/steam/.cache/fex/ \
    -e MESA_SHADER_CACHE_MAX_SIZE=512M \
    -e ACTIVATE_ALL_CONTENT=true --env-file "$env_file" \
    --mount "type=bind,src=$BASE/server-data,dst=/home/steam/core-keeper-data" \
    --mount "type=bind,src=$BASE/server-files,dst=/home/steam/core-keeper-dedicated" \
    --mount "type=bind,src=$BASE/fex-cache,dst=/home/steam/.cache/fex" \
    --mount "type=bind,src=$BASE/mesa-cache,dst=/home/steam/.cache/mesa_shader_cache" \
    --mount "type=bind,src=$BASE/update-control,dst=/run/corekeeper-update" \
    "$image"
