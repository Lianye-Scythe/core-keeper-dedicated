#!/usr/bin/env bash
# Run inside a disposable image with /test-repo mounted read-only.
set -Eeuo pipefail
export PUID=1001 PGID=1001
entry=/test-repo/scripts/entry.sh
bash "$entry"
for directory in "$HOMEDIR" "$STEAMAPPDIR" "$STEAMAPPDATADIR" "$BOX64_DYNACACHE_FOLDER"; do
    test "$(cat "$directory/.corekeeper-owner")" = 1001:1001
done
# Marker fast path must avoid scanning/chowning imported files.
touch "$STEAMAPPDIR/ownership-test"
chown 0:0 "$STEAMAPPDIR/ownership-test"
bash "$entry"
test "$(stat -c '%u:%g' "$STEAMAPPDIR/ownership-test")" = 0:0
# Explicit repair and changed IDs must restore ownership.
REPAIR_PERMISSIONS=true bash "$entry"
test "$(stat -c '%u:%g' "$STEAMAPPDIR/ownership-test")" = 1001:1001
export PUID=1002 PGID=1002
bash "$entry"
test "$(stat -c '%u:%g' "$STEAMAPPDIR/ownership-test")" = 1002:1002
# No root write through a stale marker symlink.
rm "$STEAMAPPDIR/.corekeeper-owner"
ln -s "$STEAMAPPDIR/ownership-test" "$STEAMAPPDIR/.corekeeper-owner"
bash "$entry"
test ! -L "$STEAMAPPDIR/.corekeeper-owner"
test ! -s "$STEAMAPPDIR/ownership-test"
echo ENTRY_SMOKE_PASS
