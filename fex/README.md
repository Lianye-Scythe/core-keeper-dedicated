# FEX runtime notes

FEX is now the default and only supported ARM64 runtime. Build from the root
[Dockerfile](../Dockerfile); deployment, settings and automatic maintenance are
documented in the [main README](../README.md).

The ARM64 container uses Ubuntu 26.04 LTS, while the x86-64 guest RootFS remains
on Ubuntu 24.04 LTS. These userspace environments need not match each other or
the Docker host's distribution; they share the host kernel. The official stable PPA
provides `fex-emu-armv8.2`; the official RootFS manifest supplies a validated,
extracted x86-64 guest filesystem. No privileged mount or host registration is
required. Native ARM64 DepotDownloader handles Steam downloads.

`FEX_MULTIBLOCK=1 FEX_MAXINST=16` passed repeated isolated Core Keeper 1.3.0.4
boots and short multiplayer play on Oracle A1. Larger blocks failed during the
investigation; disabling multiblock was slower. This is a workload-specific
workaround, not FEX's default or evidence of a universally optimal setting.
Default SMC tracking and memory ordering remain enabled. Long-running stability
is still being evaluated. [Historical results](RESULTS.md) retain old comparison
evidence; they are not instructions to keep or deploy the removed Box64 runtime.

FEX cache directory: `/home/steam/.cache/fex` (`FEX_APP_CACHE_LOCATION`). This does
not enable FEX disk caches that are disabled by upstream defaults. Mesa cache is
separate at `/home/steam/.cache/mesa_shader_cache`, with a 512-MiB driver budget.
Neither cache belongs in save backups. Do not use `-nographics` for this game.

For parallel compatibility experiments, use independent writable game/save/cache
directories and a different Game ID. Never bind the production saves into two
running containers. Keep game build, resource limits and world contents equal
when making performance comparisons.

`run-production.sh` is an optional managed `/data/corekeeper` bootstrap, using a
root-owned `/etc/corekeeper-fex.env` and an immutable image reference in
`/data/corekeeper/ops/fex-image-ref`. It refuses to replace an existing container
and never resets saves. The scheduled updater preserves settings from the current
container rather than hardcoding this host's private join ID into the repository.

Sources: [FEX prerequisites](https://github.com/FEX-Emu/FEX#prerequisites),
[official RootFS manifest](https://rootfs.fex-emu.gg/RootFS_links.json),
[configuration defaults](https://github.com/FEX-Emu/FEX/blob/FEX-2609.1/FEXCore/Source/Interface/Config/Config.json.in).
