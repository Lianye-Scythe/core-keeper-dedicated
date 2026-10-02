#!/usr/bin/env bash
set -e
test "$(id -u)" = "$PUID"
test "$(id -g)" = "$PGID"
test -w "$STEAMAPPDIR"
test -w "$STEAMAPPDATADIR"
test -w "$BOX64_DYNACACHE_FOLDER"
echo ENTRY_SMOKE_SETUP_OK
