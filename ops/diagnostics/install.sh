#!/usr/bin/env bash
# Optional configured host deployment. Does not recreate the game.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
enable_core=false
if [[ ${1:-} == --enable-core-routing && $# == 1 ]]; then
    enable_core=true
elif [[ $# != 0 ]]; then
    echo 'Usage: install.sh [--enable-core-routing]' >&2
    exit 1
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for dependency in python3 docker lsof curl timeout systemctl install; do
    command -v "$dependency" >/dev/null || { echo "Missing dependency: $dependency" >&2; exit 1; }
done
settings=$(python3 -B "$source_dir/host_config.py" settings)
read -r base _container <<< "$settings"
for path in "$base" "$base/server-data" "$base/server-files"; do
    [[ -d $path && ! -L $path ]] || { echo "Unexpected directory: $path" >&2; exit 1; }
done
python3 -B "$source_dir/host_config.py" check-container
if $enable_core; then
    [[ -x /usr/share/apport/apport ]] || { echo 'Only Ubuntu Apport core routing is supported.' >&2; exit 1; }
    python3 -B "$source_dir/core-config.py" --check
fi
for path in "$base/diagnostics" "$base/diagnostics/network" "$base/runtime-test"; do
    [[ ! -L $path ]] || { echo "Refusing symlink: $path" >&2; exit 1; }
    install -d -o root -g root -m 0700 "$path"
done
# Leave game-owned log directory ownership unchanged.
[[ ! -L $base/server-files/logs ]]
[[ -d $base/server-files/logs ]] || { echo 'Wait until the game creates its logs directory.' >&2; exit 1; }
install -d -m 0755 /usr/local/libexec
install -m 0644 "$source_dir/host_config.py" /usr/local/libexec/host_config.py
install -m 0755 "$source_dir/crash-evidence.py" /usr/local/libexec/corekeeper-crash-evidence
install -m 0755 "$source_dir/network-evidence.py" /usr/local/libexec/corekeeper-network-evidence
install -m 0755 "$source_dir/retention.py" /usr/local/libexec/corekeeper-diagnostics-retention
for unit in corekeeper-crash-evidence.service corekeeper-network-evidence.service \
            corekeeper-diagnostics-retention.service corekeeper-diagnostics-retention.timer; do
    install -m 0644 "$source_dir/$unit" /etc/systemd/system/
done
python3 -B "$source_dir/host_config.py" dropins
if $enable_core; then
    install -m 0755 "$source_dir/core-router.sh" /usr/local/sbin/corekeeper-core-router
    python3 -B "$source_dir/core-config.py"
    sysctl -p /etc/sysctl.d/90-corekeeper-crash.conf
fi
systemctl daemon-reload
systemctl enable --now corekeeper-crash-evidence.service corekeeper-network-evidence.service \
    corekeeper-diagnostics-retention.timer
# Reload observers when updating an existing installation, never the game.
systemctl restart corekeeper-crash-evidence.service corekeeper-network-evidence.service
echo 'Observers and retention enabled. No game restart was requested.'
echo 'Core dumps need the explicit routing option and a container core ulimit; see ops/diagnostics/README.md.'
