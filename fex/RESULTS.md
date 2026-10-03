# Oracle A1 compatibility test — 2026-10-04

Status: experimental image and isolated test tooling are prepared; Core Keeper
has **not** successfully loaded a world under this candidate. Do not promote it.
Production stayed on Box64 without restart throughout these tests.

Candidate: `ghcr.io/lianye-scythe/core-keeper-dedicated@sha256:624aeff81ef42c5abb4b282fc21a898a28a99650b43df73226a7030aaf2fbc8b`.
FEX official PPA package: `fex-emu-armv8.2` version `2609.1-1~n`.
Official Ubuntu 24.04 RootFS: 2026-08-11, manifest XXH3-64 `3517e0e5ea25a473`.
Game: 1.3.0.4-511d, Unity 6000.0.59f2; copied files from the running Box64 server.
The guest software renderer reported llvmpipe LLVM 20.1.8 / Mesa 26.1.6.
Host kernel: `7.0.0-1013-oracle`; native container Mesa package: `25.2.8-0ubuntu0.24.04.4`.

Both attempts used independent world-1 backup copies, a test-only Game ID, native
ARM64 Ubuntu 24.04 container, 1 CPU / 10 GiB limit, default TSO, and no privileged
container. No explicit graphics-thunk profile was supplied. These resource limits
protect production and are not suitable for an equal-resource speed comparison.

| SMC mode | Observed result |
| --- | --- |
| Default page tracking (`FEX_SMCCHECKS=1`) | Engine and Steam initialized; data blocks loaded; then Unity reported SIGSEGV (`code:2`). Container exited 139, `OOMKilled=false`, before world readiness. |
| Full validation (`FEX_SMCCHECKS=2`) | Unity reported fatal SIGSEGVs (`code:1` and `code:2`) during early initialization; no world readiness. Graceful stop did not complete within 120 seconds, so Docker killed the test (exit 137; this was a requested stop, not evidence of OOM). |

This is an image/guest/runtime compatibility failure, **not proof that the FEX
translator alone is responsible**, nor an explanation for earlier Box64 failures.
A useful next investigation would capture guest RIP and a symbolized native
backtrace, and separately vary the guest libraries/graphics path. The production
crash collector deliberately scopes itself to production save files; it does not
currently provide a full FEX-test core/backtrace.

Raw logs and inspections remain private on the VPS under
`/data/corekeeper/runtime-test`, including bounded previous-container evidence.
No client gameplay or stability/performance comparison has been completed.

There is also an [upstream Valheim/Unity report on Oracle Ampere](https://github.com/FEX-Emu/FEX/issues/5985)
with SIGSEGVs under FEX; its fault addresses and circumstances differ, so it does
not establish that our failure has the same cause.
