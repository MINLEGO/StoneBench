# Issue #13 — original Minecraft evidence

Delivered runtime source: `3630393352ce0c6f3344cd62e0e2c72efbd0f9cc`. Export source head: `f024401c2891b8e69b6da1d21b3659031967e50e` (only exporter changed after the runtime head). Subsequent evidence-only commits do not change the tested runtime.

`minecraft-proof.zip` contains 7798 original entries (40,864,425 bytes): source files, final JAR, launcher logs, original JSON/JSONL observations/checkpoint metadata/request results and the unit/sprint summary. Every entry and all seven copied controller JARs were read back and hash-checked. Minecraft worlds, external libraries/caches and native full rule texts stay local. `manifest.json` maps paths to SHA-256, Git blobs and versions.

- Archive SHA-256: `d90afa2c5f0af4e70654e76164272279f496b99b33fcbb10268e7c51cfc15de9`.
- JAR SHA-256: `8157df083019cab7f19238e53f6f0ffa49208d0b72f64b6a378fca7c000581d1`.
- Runtime: Minecraft 1.21.11, Yarn 1.21.11+build.3, Fabric Loader 0.19.5, Java 21.0.12, MCP SDK 1.26.0, Gradle 9.2.1, Loom 1.14.10.

## Executed checks

Java build succeeded (41s), including existing Java checkpoint, geometry, input, observation, rest and streaming checks. Python measurements rules: 7 passed; verification protocol: 8 passed; checkpoint storage: 9 passed.

Final real MCP suite: 1 scenario passed in 143.838s; both launcher journals passed. Source root `tests-0f0c500904144f97bf9572bc3b8574c0` contains a conformant copy-verification result and an independently cancelled request with durable `verification_interrupted`, false conformity and retained copies. Source-world snapshots stayed equal. The positive vanilla 2x2 fixture proves connected volume 300, repeater opening/closing 6gt (2gt adaptation +4gt response), direct diagnostic 4gt, later circuit movement and later rest. The separate native observer fixture proves cumulative volume 10 while endpoint volume is 8. Assertions cover adapter/door exclusions, retained piston components and missing movement/extent/completeness/memory negative controls. Expectations and rule paragraphs are documented in [measurements.md](../../measurements.md).

Real unit/sprint comparison: 56 operations exactly compared; scenario passed in 285.568s with successful launcher checks. The archived summary retains expanded state/NBT/runtime/event/coverage hashes. Native sprint remains the default, unit the reference option. Java instrumentation is identical in these two runs and the final measurement run; the later Python change orders same-tick received-power edges and is covered by the final run.

## Reproduction

Use the contract's readonly SDK and server seed, independent runtime/cache and available dedicated ports. PowerShell commands run from the worktree:

```powershell
./scripts/build.ps1 -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Offline
./scripts/test-server.ps1 -Suite tests/measurements.py -AcceptEula -SkipBuild -UseCheckpointSupervisor -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Python 'C:/Users/minle/.codex/worktrees/issue-5/StoneBench/app/controller/.runtime/test-venv/Scripts/python.exe' -ServerCacheSource 'C:/Users/minle/Documents/projets/StoneBench/app/prototype-transition/.runtime/server-cache' -BaseMcpPort 19565 -BaseGamePort 26381
$env:STONEBENCH_SPRINT_EVIDENCE='app/controller/.runtime/measurements-sprint.json'
./scripts/test-server.ps1 -Suite tests/transition_sprint.py -AcceptEula -SkipBuild -TickExecution unit -SecondTickExecution sprint -InitialPreparationTicks 120 -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Python 'C:/Users/minle/.codex/worktrees/issue-5/StoneBench/app/controller/.runtime/test-venv/Scripts/python.exe' -ServerCacheSource 'C:/Users/minle/Documents/projets/StoneBench/app/prototype-transition/.runtime/server-cache' -BaseMcpPort 19565 -BaseGamePort 26381
```

Measurement run uses working MCP 19565/19566, game 26381/26382 and owned copy MCP 19567/19568, game 26383/26384. Only test-owned processes are stopped. Export with `tests/measurements_archive.py` while the six named launcher/check logs remain in the root. Final logs are archived; local historical failed runs are retained in the ignored controller runtime. A relaunch without `-UseCheckpointSupervisor` was refused before mutation, then corrected; it is not the successful final proof.

## Limits and downstream contract

Normal timing is movement **start +2gt**, not observed completion +2gt; instant is start, short-pulse extension is start + proven 0..2gt received pulse. Native instant/0/1gt montages are not runtime-proven here; arithmetic is tested and unclassified/missing events stay indeterminate. Alpha instrumentation is bounded, not universal circuit necessity or unknown memory coverage. No community-record claim or fused score; nonconformant results retain diagnostics. Full #12's long scenario matrix was not repeated; focused real copy/preservation/cancellation and protocol/storage regressions cover this change.

For #14/#15: reuse asynchronous request/status/cancel, independent-copy lease/checkpoint hashes/rollback, per-transition 36000gt and derived 432000gt bound; no added global quota. Keep per-transition `measurements`, repeater summary objectives, direct diagnostic, timestamps, sources/gaps and `record_eligibility=not_verified`. Game ticks are separate from wall time. Cancellation and final working-world validation can revoke interpretation. No paid campaign executed or authorized by this delivery.
