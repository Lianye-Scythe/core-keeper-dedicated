# Experimental FEX ARM64 variant

**Not a production fallback yet.** On the managed Oracle A1 VPS, Core Keeper
1.3.0.4 failed during initialization in both tested SMC modes. Image/guest smoke
tests pass, but they do not prove game compatibility. See [measured results](RESULTS.md).

This variant does not replace `latest` (Box64). Build/publish uses only `fex-test`
and commit-labelled `fex-<commit>` tags. After pulling, use its `@sha256:...`
digest for an exact A/B build: rebuilding the same commit can refresh dependencies.

The native ARM64 container and guest RootFS use Ubuntu 24.04 LTS. FEX comes from
the official `ppa:fex-emu/fex` (`fex-emu-armv8.2`); package versions are refreshed
when building, not modified on game startup. The official RootFS manifest selects
its current Ubuntu 24.04 SquashFS, validates the published XXH3-64, and records
the URL/hash/SHA-256 in `/opt/fex-rootfs-source.json`.

An extracted RootFS avoids FUSE/privileged mounts. No host binfmt registration,
`--privileged`, forced CPU affinity, TSO-disable hacks or graphics-disable flags
are requested. FEX memory-ordering and SMC settings remain at upstream defaults.
The guest smoke test checks x86 programs on a native ARM64 runner before publishing;
this is not proof of Core Keeper stability.

Use the same game build, world snapshot, parameters and resource limits in both
runtimes. A different Game ID and independent **writable copies** of game files,
world saves, Mesa cache and emulator cache are mandatory for a parallel test.
Never mount the production save directory into two running servers. Do not use
`-nographics`: the shipped server README says generation requires graphics.

Persistent FEX cache: `/home/steam/.cache/fex` (`FEX_APP_CACHE_LOCATION`). Mesa cache:
`/home/steam/.cache/mesa_shader_cache` (driver budget 512 MiB). Do not share Mesa
caches between variants: guest libraries and native thunk choices can differ.

Build locally on ARM64:

```sh
docker build --platform linux/arm64 -f fex/Dockerfile -t corekeeper-fex:test .
docker run --rm --network none --entrypoint bash -v "$PWD:/test-repo:ro" \
  corekeeper-fex:test /test-repo/tests/fex-image-smoke.sh
```

Preparation and test-switching on the managed VPS use `runtime-test.sh`:

```sh
sudo bash runtime-test.sh prepare
# Pull a smoke-tested immutable image, then supply its exact tag:
sudo docker pull ghcr.io/lianye-scythe/core-keeper-dedicated:fex-<commit>
sudo bash runtime-test.sh start fex ghcr.io/lianye-scythe/core-keeper-dedicated@sha256:<digest>
sudo bash runtime-test.sh status
sudo bash runtime-test.sh stop
sudo bash runtime-test.sh start box64
```

Preparation uses the newest complete world backup and separate copies of the
installed game files; updates are gated off. It never overwrites existing test
saves. Both engines initially have the same snapshot and a shared **test-only**
Game ID, and cannot run simultaneously through this tool. Subsequent play changes
each engine's own copy independently. Reset/rebaseline is an explicit manual task.
The test has a 1-core/10-GiB limit and lower CPU scheduling priority to protect the
active production server. This is a compatibility test, **not an equal-resource
performance benchmark**. No ports are published; join through the test Game ID.
Only one previous-container log/inspection is retained when switching.

An optional diagnostic mode uses upstream's slower full self-modifying-code
validation rather than its default page tracking. It never disables SMC or TSO:

```sh
sudo env FEX_TEST_SMC_MODE=full bash runtime-test.sh start fex <image-digest>
```

Production remains on Box64 and its scheduled updater still targets
Box64. Promoting FEX to production requires an explicit maintenance action and
updater/diagnostics integration; merely starting the test does not promote it.

Known comparison limitation: this FEX image has a different guest/native library
stack from the Bookworm Box64 image. An improvement can justify choosing the image,
but does not by itself prove a Box64 emulator bug.

Sources: [FEX prerequisites](https://github.com/FEX-Emu/FEX#prerequisites),
[official RootFS manifest](https://rootfs.fex-emu.gg/RootFS_links.json).
