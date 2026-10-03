#!/bin/bash
# Isolated test controller for the managed Oracle A1 installation; run with sudo.
set -Eeuo pipefail
BASE=/data/corekeeper/runtime-test
PRODUCTION=core-keeper-dedicated
TEST=corekeeper-runtime-test
SOURCE=/data/corekeeper
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
mountpoint -q /data || { echo '/data is not mounted; refusing to use the system disk.' >&2; exit 1; }
exec 9>/run/lock/corekeeper-runtime-test.lock
flock -n 9 || { echo 'Another test operation is running.' >&2; exit 1; }

case ${1:-status} in
prepare)
    [[ ! -e $BASE ]] || { echo 'Already prepared; existing test saves are preserved.'; exit 0; }
    [[ $(docker inspect -f '{{.State.Running}}' "$PRODUCTION") == true ]]
    backup=$(find "$SOURCE/backups" -maxdepth 1 -type f -name 'corekeeper-world-*.tar.gz' -printf '%f\n' | sort | tail -n 1)
    [[ -n $backup ]] || { echo 'No world backup available.' >&2; exit 1; }
    # Validate paths and reject links/devices before extracting a privileged archive.
    python3 - "$SOURCE/backups/$backup" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1]) as archive:
    members = archive.getmembers()
    if not members:
        raise SystemExit('Empty backup')
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'server-data':
            raise SystemExit('Unsafe backup path: ' + member.name)
        if not (member.isdir() or member.isfile()):
            raise SystemExit('Unsafe backup entry: ' + member.name)
PY
    stage=$(mktemp -d "$SOURCE/.runtime-test-XXXXXX")
    chmod 700 "$stage"
    # A failed preparation is left in this staging directory for inspection.
    tar -xzf "$SOURCE/backups/$backup" -C "$stage" --no-same-owner
    mv "$stage/server-data" "$stage/baseline-data"
    config="$stage/baseline-data/ServerConfig.json"
    [[ -f $config ]]
    test_id="FEX$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"
    jq --arg id "$test_id" '.gameId = $id' "$config" > "$stage/config.tmp"
    mv "$stage/config.tmp" "$config"
    image=$(docker inspect -f '{{.Image}}' "$PRODUCTION")
    jq -n --arg backup "$backup" --arg id "$test_id" --arg image "$image" \
        --arg timestamp "$(date -Iseconds)" \
        '{backup:$backup,gameId:$id,box64Image:$image,preparedAt:$timestamp}' > "$stage/baseline.json"
    # These are independent writable copies, never hard links to production.
    for runtime in box64 fex; do
        cp -a --reflink=auto "$stage/baseline-data" "$stage/server-data-$runtime"
        cp -a --reflink=auto "$SOURCE/server-files" "$stage/server-files-$runtime"
        mkdir -p "$stage/cache-$runtime" "$stage/mesa-$runtime"
        chown -R 1001:1001 "$stage/server-data-$runtime" "$stage/server-files-$runtime" \
            "$stage/cache-$runtime" "$stage/mesa-$runtime"
    done
    mv "$stage" "$BASE"
    echo "Prepared isolated world copies. Test Game ID: $test_id"
    ;;
start)
    runtime=${2:-}
    [[ $runtime == box64 || $runtime == fex ]] || { echo 'Usage: runtime-test.sh start box64|fex [immutable-image]' >&2; exit 1; }
    [[ -f $BASE/baseline.json ]] || { echo 'Run prepare first.' >&2; exit 1; }
    [[ $(docker inspect -f '{{.State.Running}}' "$TEST" 2>/dev/null || true) != true ]] || {
        echo 'A test is already running; stop it before switching.' >&2; exit 1;
    }
    image=${3:-}
    if [[ -z $image && $runtime == box64 ]]; then
        image=$(jq -r .box64Image "$BASE/baseline.json")
    fi
    [[ -n $image ]] || { echo 'Supply a verified immutable fex-<commit> image.' >&2; exit 1; }
    docker image inspect "$image" >/dev/null
    if [[ $runtime == fex ]]; then
        [[ $(docker image inspect -f '{{range .Config.Env}}{{if eq . "COREKEEPER_RUNTIME=fex"}}yes{{end}}{{end}}' "$image") == yes ]]
    fi
    runtime_env=()
    if [[ $runtime == fex ]]; then
        case ${FEX_TEST_SMC_MODE:-mtrack} in
            mtrack) runtime_env+=(-e FEX_SMCCHECKS=1) ;;
            full) runtime_env+=(-e FEX_SMCCHECKS=2) ;;
            *) echo 'FEX_TEST_SMC_MODE must be mtrack or full (never none).' >&2; exit 1 ;;
        esac
    fi
    # Preserve stopped-container logs before replacing only this exact test container.
    if docker inspect "$TEST" >/dev/null 2>&1; then
        docker logs --timestamps "$TEST" > "$BASE/previous-container.log" 2>&1 || true
        docker inspect "$TEST" > "$BASE/previous-container.json"
        docker rm "$TEST" >/dev/null
    fi
    cache_target=/home/steam/.cache/box64
    [[ $runtime != fex ]] || cache_target=/home/steam/.cache/fex
    test_id=$(jq -r .gameId "$BASE/baseline.json")
    world_index=$(jq -r '.world // 1' "$BASE/baseline-data/ServerConfig.json")
    docker run -d "${runtime_env[@]}" --name "$TEST" --restart no --stop-timeout 120 \
        --cpus 1 --cpu-shares 256 --memory 10g --memory-swap 10g \
        --log-opt max-size=10m --log-opt max-file=3 \
        -e PUID=1001 -e PGID=1001 -e COREKEEPER_RUNTIME="$runtime" \
        -e USE_DEPOT_DOWNLOADER=true -e UPDATE_GATE_ENABLED=true \
        -e WORLD_INDEX="$world_index" -e WORLD_NAME=CoreKeeperRuntimeTest \
        -e GAME_ID="$test_id" -e ACTIVATE_ALL_CONTENT=true \
        -e BOX64_DYNACACHE_FOLDER=/home/steam/.cache/box64 \
        -e BOX64_DYNACACHE_LIMIT=2048 -e BOX64_LOG=0 \
        -e FEX_APP_CACHE_LOCATION=/home/steam/.cache/fex/ \
        -e MESA_SHADER_CACHE_MAX_SIZE=512M \
        -v "$BASE/server-data-$runtime:/home/steam/core-keeper-data" \
        -v "$BASE/server-files-$runtime:/home/steam/core-keeper-dedicated" \
        -v "$BASE/cache-$runtime:$cache_target" \
        -v "$BASE/mesa-$runtime:/home/steam/.cache/mesa_shader_cache" "$image"
    echo "Started $runtime test with a 1-core safety limit. Test Game ID: $test_id"
    ;;
stop)
    docker stop -t 120 "$TEST"
    ;;
status)
    [[ ! -f $BASE/baseline.json ]] || jq . "$BASE/baseline.json"
    docker inspect -f 'State={{.State.Status}} Started={{.State.StartedAt}} Exit={{.State.ExitCode}} Image={{.Config.Image}}' "$TEST" 2>/dev/null || true
    ;;
*) echo 'Usage: runtime-test.sh prepare|start box64|fex [image]|stop|status' >&2; exit 1 ;;
esac
