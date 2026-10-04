# Oracle A1 compatibility test — 2026-10-04

Status: Core Keeper **successfully loaded a world** using bounded multiblock
translation (`FEX_MULTIBLOCK=1 FEX_MAXINST=16`). This is an experimental startup
workaround, not multiplayer or long-running stability validation. Production
was on Box64 during the isolated trials. Later, the owner chose FEX production
with a fresh world 0, after a short successful multiplayer test. Long-running
stability is still unverified; see the deployment note in README.md.

Candidate: `ghcr.io/lianye-scythe/core-keeper-dedicated@sha256:624aeff81ef42c5abb4b282fc21a898a28a99650b43df73226a7030aaf2fbc8b`.
FEX official PPA package: `fex-emu-armv8.2` version `2609.1-1~n`.
Official Ubuntu 24.04 RootFS: 2026-08-11, manifest XXH3-64 `3517e0e5ea25a473`.
Game: 1.3.0.4-511d, Unity 6000.0.59f2; copied files from the running Box64 server.
The guest software renderer reported llvmpipe LLVM 20.1.8 / Mesa 26.1.6.
Host kernel: `7.0.0-1013-oracle`; native container Mesa package: `25.2.8-0ubuntu0.24.04.4`.

The original two attempts used independent world-1 backup copies, a test-only Game ID, native
ARM64 Ubuntu 24.04 container, 1 CPU / 10 GiB limit, default TSO, and no privileged
container. No explicit graphics-thunk profile was supplied. These resource limits
protect production and are not suitable for an equal-resource speed comparison.

| SMC mode | Observed result |
| --- | --- |
| Default page tracking (`FEX_SMCCHECKS=1`) | Engine and Steam initialized; data blocks loaded; then Unity reported SIGSEGV (`code:2`). Container exited 139, `OOMKilled=false`, before world readiness. |
| Full validation (`FEX_SMCCHECKS=2`) | Unity reported fatal SIGSEGVs (`code:1` and `code:2`) during early initialization; no world readiness. Graceful stop did not complete within 120 seconds, so Docker killed the test (exit 137; this was a requested stop, not evidence of OOM). |

This is an image/guest/runtime compatibility failure, **not proof that the FEX
translator alone is responsible**, nor an explanation for earlier Box64 failures.
Subsequent native/guest fault captures found a guest instruction address outside
its mapped Mono JIT region, but did not prove the responsible FEX implementation
bug. The production
crash collector deliberately scopes itself to production save files; it does not
currently provide a full FEX-test core/backtrace.

Raw logs and inspections remain private on the VPS under
`/data/corekeeper/runtime-test`, including bounded previous-container evidence.
A short client gameplay test subsequently succeeded. No controlled gameplay
performance comparison or long-running stability test has been completed.

## Bounded multiblock startup optimization

Later trials used the same immutable candidate/game build, fresh copies of the
same test-world snapshot, 2 CPU / 10 GiB limits, default mtrack and TSO, and
test-only warmed cache directories. No production files were mounted writable.
Timing runs from the engine log marker to the first ready `timescale=0` marker.

| Translation configuration | Startup result | ECS intervals combined |
| --- | --- | --- |
| Multiblock off, MaxInst 5000 | Ready in 629.89 s (10 min 30 s) | 512.05 s |
| Multiblock on, MaxInst 64 | Fatal signal before world readiness | Not completed |
| Multiblock on, MaxInst 16, first run | Ready in 250.58 s (4 min 11 s) | 169.89 s |
| Multiblock on, MaxInst 16, repeat run | Ready in 268.04 s (4 min 28 s) | 186.62 s |

The two bounded-16 runs reduced observed startup time by approximately 57–60%.
The baseline included low-rate diagnostic sampling; optimized runs did not, so
this is an observed operational comparison, not a precision emulator benchmark.
Do not interpret it as a 60% gameplay FPS improvement or proof of crash-free play.
The historical test controller used a 1-CPU cap; these timings used 2.
That A/B controller has since been removed. The production FEX image defaults to
bounded-16 without weakening TSO/SMC and imposes no CPU quota itself.

Private first-run evidence: `trial-bounded16.8GBqLi`; failed-64 evidence:
`trial-bounded64.GnZGhF`; repeat evidence: `trial-bounded16.2S4oqU`, under
`/data/corekeeper/runtime-test`. Both successful trials were stopped by the
controller after readiness (exit 143, not OOM); they are not unattended servers.

There is also an [upstream Valheim/Unity report on Oracle Ampere](https://github.com/FEX-Emu/FEX/issues/5985)
with SIGSEGVs under FEX; its fault addresses and circumstances differ, so it does
not establish that our failure has the same cause.
