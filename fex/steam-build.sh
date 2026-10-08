#!/bin/bash
# Query Steam directly; never touch installed game files or persist account credentials.
set -euo pipefail
probe=$(mktemp -d /tmp/corekeeper-steam-metadata.XXXXXX)
trap 'rm -rf -- "$probe"' EXIT
timeout 150s DepotDownloader -app 1963720 -depot 1963722 -branch public -os linux -osarch 64 \
    -manifest-only -dir "$probe" >"$probe/output.log" 2>&1
shopt -s nullglob
manifests=("$probe"/manifest_1963722_*.txt)
if [[ ${#manifests[@]} != 1 ]]; then
    echo "Steam did not return exactly one Linux server manifest." >&2
    exit 1
fi
manifest=${manifests[0]##*/manifest_1963722_}
manifest=${manifest%.txt}
[[ $manifest =~ ^[0-9]+$ ]]
printf 'manifest:1963722:%s\n' "$manifest"
