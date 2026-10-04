#!/bin/sh
# Bound capture duration so a stalled collector cannot block restart indefinitely.
exec /usr/bin/timeout 180 /usr/local/libexec/corekeeper-crash-evidence core "$@"
