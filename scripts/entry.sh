#!/bin/bash
set -e
source "${SCRIPTSDIR}/helper-functions.sh"

# Scan persistent directories once per UID/GID, not on every restart.
prepare_owner() {
    local directory="$1" marker
    marker="${directory}/.corekeeper-owner"
    mkdir -p "${directory}"
    if [[ "${REPAIR_PERMISSIONS:-false}" != true ]] \
        && [[ -f "${marker}" && ! -L "${marker}" ]] \
        && [[ "$(cat "${marker}")" == "${PUID}:${PGID}" ]] \
        && [[ "$(stat -c '%u:%g' "${directory}")" == "${PUID}:${PGID}" ]]; then
        return
    fi
    LogAction "INITIALIZING OWNERSHIP: ${directory}"
    # Exclude separately managed data and read-only script mounts from HOME.
    if [[ "${directory}" == "${HOMEDIR}" ]]; then
        find "${directory}" \( -path "${STEAMAPPDIR}" -o -path "${STEAMAPPDATADIR}" \
            -o -path "${SCRIPTSDIR}" -o -path "${FEX_APP_CACHE_LOCATION}" \) -prune \
            -o \( ! -uid "${PUID}" -o ! -gid "${PGID}" \) \
            -exec chown -h "${PUID}:${PGID}" {} +
    else
        find "${directory}" \( ! -uid "${PUID}" -o ! -gid "${PGID}" \) \
            -exec chown -h "${PUID}:${PGID}" {} +
    fi
    # The reserved marker must not redirect root writes through a symlink.
    rm -f -- "${marker}"
    printf '%s\n' "${PUID}:${PGID}" >"${marker}"
    chown "${PUID}:${PGID}" "${marker}"
}

FEX_APP_CACHE_LOCATION="${FEX_APP_CACHE_LOCATION:-${HOMEDIR}/.cache/fex}"
export FEX_APP_CACHE_LOCATION

# From: https://github.com/thijsvanloef/palworld-server-docker/blob/32ffe489daecbc332701592f2facf0fe3237c65f/scripts/init.sh#L15
# Checks for root, updates UID and GID of user steam
# and updates folders owners
if [[ "$(id -u)" -eq 0 ]] && [[ "$(id -g)" -eq 0 ]]; then
    if [[ ! "${PUID}" =~ ^[1-9][0-9]*$ || ! "${PGID}" =~ ^[1-9][0-9]*$ ]]; then
        LogError "PUID and PGID must be positive numeric IDs."
        exit 1
    fi
    if [[ "${PUID}" -ne 0 ]] && [[ "${PGID}" -ne 0 ]]; then
        LogAction "EXECUTING USERMOD"
        if [[ "$(id -u "${USER}")" != "${PUID}" ]]; then
            # usermod otherwise recursively chowns HOME itself, including RO
            # bind mounts. Our explicit ownership preparation handles it instead.
            account_home="$(getent passwd "${USER}" | cut -d: -f6)"
            usermod -d /nonexistent "${USER}"
            usermod -o -u "${PUID}" "${USER}"
            usermod -d "${account_home}" "${USER}"
        fi
        [[ "$(id -g "${USER}")" == "${PGID}" ]] || groupmod -o -g "${PGID}" "${USER}"
        for directory in "${HOMEDIR}" "${STEAMAPPDIR}" "${STEAMAPPDATADIR}" "${FEX_APP_CACHE_LOCATION}"; do
            prepare_owner "${directory}"
        done
        for directory in "${STEAMAPPDIR}" "${STEAMAPPDATADIR}" "${FEX_APP_CACHE_LOCATION}"; do
            if ! gosu "${USER}" test -w "${directory}"; then
                LogError "${directory} is not writable by ${USER}. Check permissions or use REPAIR_PERMISSIONS=true."
                exit 1
            fi
        done
    else
        LogError "Running as root is not supported, please fix your PUID and PGID!"
        exit 1
    fi
elif [[ "$(id -u)" -eq 0 ]] || [[ "$(id -g)" -eq 0 ]]; then
    LogError "Running as root is not supported, please fix your user!"
    exit 1
fi

if ! [ -w "${STEAMAPPDIR}" ]; then
    LogError "${STEAMAPPDIR} is not writable."
    exit 1
fi

if ! [ -w "${STEAMAPPDATADIR}" ]; then
    LogError "${STEAMAPPDATADIR} is not writable."
    exit 1
fi

#Restart cleanup
if [ -f "/tmp/.X99-lock" ]; then rm /tmp/.X99-lock; fi

if [[ "$(id -u)" -eq 0 ]]; then
    exec gosu "${USER}" bash "${SCRIPTSDIR}/setup.sh"
else
    exec bash "${SCRIPTSDIR}/setup.sh"
fi
