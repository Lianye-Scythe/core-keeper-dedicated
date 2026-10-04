#!/bin/bash
source "${SCRIPTSDIR}/helper-functions.sh"

# Switch to workdir
cd "${STEAMAPPDIR}" || exit

### Function for gracefully shutdown
function kill_corekeeperserver {
    if [[ -n "$ckpid" ]] && kill -0 "$ckpid" 2>/dev/null; then
        kill "$ckpid"
        wait "$ckpid"
    fi

    if [[ -n "$xvfbpid" ]] && kill -0 "$xvfbpid" 2>/dev/null; then
        kill "$xvfbpid"
        wait "$xvfbpid"
    fi

    # Sends stop message
    if [[ "${DISCORD_SERVER_STOP_ENABLED,,}" == true ]]; then
        wait=true
        SendDiscordMessage "$DISCORD_SERVER_STOP_TITLE" "$DISCORD_SERVER_STOP_MESSAGE" "$DISCORD_SERVER_STOP_COLOR" "$wait"
    fi
}

trap kill_corekeeperserver EXIT

if [ -f "GameID.txt" ]; then rm GameID.txt; fi
if [ -f "GameInfo.txt" ]; then rm GameInfo.txt; fi

# Compile Parameters
# Populates `params` array with parameters.
# Creates `logfile` var with log file path.
source "${SCRIPTSDIR}/compile-parameters.sh"

# Create the log file and folder.
mkdir -p "${STEAMAPPDIR}/logs"
# `compile-parameters.sh` sets logfile and params in the current shell.
# shellcheck disable=SC2154
touch "$logfile"

# Start Xvfb
Xvfb :99 -screen 0 1x1x24 -nolisten tcp &
xvfbpid=$!

# Get the architecture using dpkg
architecture=$(dpkg --print-architecture)

# Start Core Keeper Server
if [ "$architecture" == "arm64" ]; then
    runtime="${COREKEEPER_RUNTIME:-fex}"
    case "${runtime}" in
        fex)
            emulator=/usr/bin/FEX
            if [[ "${USE_DEPOT_DOWNLOADER}" != true || ! -d "${FEX_ROOTFS:-}" ]]; then
                LogError "FEX requires DepotDownloader and an extracted FEX_ROOTFS."
                exit 1
            fi
            ;;
        *) LogError "Unsupported COREKEEPER_RUNTIME: ${runtime}"; exit 1 ;;
    esac
    if [[ ! -x "${emulator}" ]]; then
        LogError "Emulator is missing: ${emulator}"
        exit 1
    fi
    # `compile-parameters.sh` sets params in the current shell.
    # shellcheck disable=SC2154
    DISPLAY=:99 LD_LIBRARY_PATH="${STEAMCMDDIR}/linux64:/usr/lib:${LD_LIBRARY_PATH#:}" "${emulator}" ./CoreKeeperServer "${params[@]}" &
else
    LogError "This image supports ARM64 with FEX only."
    exit 1
fi
ckpid=$!

LogDebug "Started server process with pid ${ckpid}"

# Monitor server logs for player join/leave, server start, and server stop
source "${SCRIPTSDIR}/logfile-parser.sh"
tail --pid "$ckpid" -f "$logfile" | LogParser &

wait $ckpid
