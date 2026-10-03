#!/usr/bin/env bash
# Execute inside the FEX image on native ARM64. No game or save access.
set -Eeuo pipefail
test "$(dpkg --print-architecture)" = arm64
test "${COREKEEPER_RUNTIME}" = fex
test -x /usr/bin/FEXInterpreter
test -d "${FEX_ROOTFS}/usr/lib/x86_64-linux-gnu"
test -s /opt/fex-rootfs-source.json
gosu steam /usr/bin/FEXInterpreter "${FEX_ROOTFS}/usr/bin/true"
gosu steam /usr/bin/FEXInterpreter "${FEX_ROOTFS}/usr/bin/printf" 'FEX_GUEST_SMOKE_PASS\n'
