#!/bin/bash

source "${SCRIPTSDIR}/mod-manager.sh"

mkdir -p "${STEAMAPPDIR}" || true

UPDATE_PERMIT_FILE="${UPDATE_PERMIT_FILE:-/run/corekeeper-update/apply-update}"
UPDATE_PERMIT_MAX_AGE_SECONDS="${UPDATE_PERMIT_MAX_AGE_SECONDS:-3600}"

RUN_UPDATE=false
if [[ "${UPDATE_GATE_ENABLED,,}" == "true" ]]; then
    # A new server has to download its files once even when no maintenance permit exists.
    if [[ ! -x "${STEAMAPPDIR}/CoreKeeperServer" ]]; then
        echo "Server files are missing; performing the initial Steam download."
        RUN_UPDATE=true
    elif [[ -f "${UPDATE_PERMIT_FILE}" ]]; then
        read -r PERMIT_EPOCH <"${UPDATE_PERMIT_FILE}" || true
        CURRENT_EPOCH="$(date +%s)"
        if [[ "${PERMIT_EPOCH:-}" =~ ^[0-9]+$ ]] \
            && [[ "${UPDATE_PERMIT_MAX_AGE_SECONDS}" =~ ^[0-9]+$ ]] \
            && (( CURRENT_EPOCH >= PERMIT_EPOCH \
                && CURRENT_EPOCH - PERMIT_EPOCH <= UPDATE_PERMIT_MAX_AGE_SECONDS )); then
            echo "Valid scheduled update permit found; checking Steam server files."
            RUN_UPDATE=true
        else
            echo "Ignoring stale or invalid Steam update permit."
            rm -f "${UPDATE_PERMIT_FILE}"
        fi
    fi
else
    # Preserve the image's original behavior unless the opt-in gate is enabled.
    RUN_UPDATE=true
fi

if [[ "${RUN_UPDATE}" == true ]]; then
    # Certify the installed Linux manifest using Steam, not a cached third-party API.
    build_before=$(bash "${SCRIPTSDIR}/steam-build.sh") || build_before=""
    rm -f "${STEAMAPPDIR}/.corekeeper-buildid"
    if [[ "${USE_DEPOT_DOWNLOADER}" == true ]]; then
        DepotDownloader -app "${STEAMAPPID}" -osarch 64 -dir "${STEAMAPPDIR}" -validate || exit $?
        DepotDownloader -app "${STEAMAPPID_TOOL}" -osarch 64 -dir "${STEAMAPPDIR}" -validate || exit $?
        chmod +x "${STEAMAPPDIR}/CoreKeeperServer"
    else
        LogError "FEX requires USE_DEPOT_DOWNLOADER=true; SteamCMD is not installed."
        exit 1
    fi

    build_after=$(bash "${SCRIPTSDIR}/steam-build.sh") || build_after=""
    manifest=${build_after#manifest:1963722:}
    if [[ -n "${build_before}" && "${build_before}" == "${build_after}" \
        && -f "${STEAMAPPDIR}/.DepotDownloader/1963722_${manifest}.manifest" ]]; then
        printf '%s\n' "${build_after}" >"${STEAMAPPDIR}/.corekeeper-buildid"
    else
        echo "Public build metadata unavailable or changed; installed build remains uncertified."
    fi

    if [[ "${UPDATE_GATE_ENABLED,,}" == "true" ]]; then
        rm -f "${UPDATE_PERMIT_FILE}"
    fi
fi

manage_mods

exec bash "${SCRIPTSDIR}/launch.sh"
