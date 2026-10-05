# Migration guide

This fork is now **FEX-only on ARM64**. The `latest` image tag no longer selects
the original Box64 runtime. This is a runtime/architecture migration, not just
a documentation rename.

## Repository and image names

- Repository: [Lianye-Scythe/core-keeper-dedicated-fex](https://github.com/Lianye-Scythe/core-keeper-dedicated-fex).
- Image: `ghcr.io/lianye-scythe/core-keeper-dedicated:fex`.
- `latest` is the same ARM64/FEX channel. The package name intentionally retains
  `core-keeper-dedicated`; it need not match the repository name.
- The upstream Box64 project remains separate; its changes are not automatically
  merged into this fork. Its attribution and original Git history are retained.

## Preserve an existing world

1. Record your container's settings and mounts, especially `WORLD_INDEX`,
   `WORLD_NAME`, `GAME_ID`, owner IDs and content activation flags. Keep private
   IDs/passwords out of public issue reports.
2. Stop the old server gracefully. Back up **all** server-data and server-files
   directories while it is stopped, and record its image digest for rollback.
3. Prepare the [FEX deployment](deployment.md) using the same save directory and
   world slot. Give FEX and Mesa their own cache directories; old Box64 caches
   are not reusable FEX caches.
4. Review [configuration precedence](configuration.md) before starting. In
   particular, the public Compose example enables all content, which can
   permanently alter an existing world.
5. Start only the new container, wait for initialization, and verify joining,
   world contents and saving. Do not run both containers on the same writable saves.

A runtime migration does not require deleting worlds or creating slot 0 again.
Switching `WORLD_INDEX` selects another save slot, not another game version.
If you intentionally want a fresh world, back up existing data first and use an
unused slot; deleting old saves is a separate, destructive choice.

## Host updater and diagnostics

Container images do not replace installed host scripts or timers. Review and
update those separately using [maintenance instructions](maintenance.md) and
the [diagnostic installer guide](../ops/diagnostics/README.md). Preserve the host's
private configuration and paths; do not overwrite them with example values.

For rollback, keep the old image digest and stopped-server backup together.
Restore matching game binaries and saves rather than guessing whether a world
written by a newer game version is compatible with an older one.
