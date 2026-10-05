#!/bin/bash
# Optional configured host bootstrap; never replaces an existing container.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 -B "$script_dir/../ops/diagnostics/host_config.py" bootstrap
