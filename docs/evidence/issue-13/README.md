# Issue #13 — original Minecraft evidence

Final corrected source/export head: `1cef0d716b033bbb71d40e1232b68efa141d13b8`. Correction `b15cc4e` makes unproved wiring membership conditional; the final code replay in `1cef0d7` matches all four serialized native boundaries after artifact hash validation. Subsequent evidence-only commits do not change the tested code. Java/JAR is unchanged from `3630393352ce0c6f3344cd62e0e2c72efbd0f9cc`.

`minecraft-proof.zip` contains 7801 original entries (41,067,784 bytes): source files, final JAR, launcher logs, original JSON/JSONL observations/checkpoint metadata/request results and the unit/sprint summary. Every entry and all seven copied controller JARs were read back and hash-checked. Minecraft worlds, external libraries/caches and native full rule texts stay local. `manifest.json` maps paths to SHA-256, Git blobs and versions.

- Archive SHA-256: `9f99a57e93bafadb1b91c7c99066379d073a90ed79f9a27b0778f7ffd17028b8`.
- JAR SHA-256: `8157df083019cab7f19238e53f6f0ffa49208d0b72f64b6a378fca7c000581d1`.
- Runtime: Minecraft 1.21.11, Yarn 1.21.11+build.3, Fabric Loader 0.19.5, Java 21.0.12, MCP SDK 1.26.0, Gradle 9.2.1, Loom 1.14.10.

## Executed checks

Java build succeeded (41s), including existing Java checkpoint, geometry, input, observation, rest and streaming checks. Python measurements rules: 8 passed; verification protocol: 8 passed; checkpoint storage: 9 passed.

Final corrected real MCP suite: 1 scenario passed in 100.332s; both launcher journals passed. Source root `tests-eb5e6d4590d54900b0531d58a8f574d3` contains a conformant copy-verification result and an independently cancelled request with durable `verification_interrupted`, false conformity and retained copies. Source-world snapshots stayed equal. Repeater opening/closing remain 6gt (2gt adaptation +4gt response), direct diagnostic 4gt, then later circuit movement and later rest.

The review regression adds a redundant stone at x1033/y81/z1025 beside the late piston. In all four real traces it receives `block_state_read`, without proof that removing it would prevent the door from functioning. The observed high volume changes from the earlier fixture's 300 to 320; exact volume is **indeterminate**, `value=null`, with distinct minimum/maximum envelopes. Other observed components/materials/movements likewise remain conditional: active participation alone does not establish counterfactual wiring necessity. The explicit input block stays in the lower envelope. The observer fixture still has an observed transient high bound of 10 against endpoint envelope 8, but its exact wiring volume is also **indeterminate/null**.

The final replay validates original artifact hashes and compares the JSON-serialized final code output for all four native boundaries. `logs/replay13-review.txt` records equality, real redundant-stone event kinds and null exact values. Eight pure tests include passive stone and repeater notifications/reads whose uncertainty extends width from 1 to 7; none publishes an exact 7. The real suite also retains adapter/door exclusions, piston observations and missing movement/extent/completeness/memory negative controls. Expectations and source paragraphs are documented in [measurements.md](../../measurements.md).

Real unit/sprint comparison: 56 operations exactly compared; scenario passed in 285.568s with successful launcher checks. The archived summary retains expanded state/NBT/runtime/event/coverage hashes. Native sprint remains the default, unit the reference option. Java instrumentation is identical in these two runs and the final measurement run; Python corrections preserve the timing/protocol and are covered by the corrected real run and final artifact replay; no Java rebuild or cadence repeat was needed.

## Reproduction

Use the contract's readonly SDK and server seed, independent runtime/cache and available dedicated ports. PowerShell commands run from the worktree:

```powershell
./scripts/build.ps1 -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Offline
$env:STONEBENCH_MEASUREMENTS_EVIDENCE='app/controller/.runtime/measurements-reviewed.json'
./scripts/test-server.ps1 -Suite tests/measurements.py -AcceptEula -SkipBuild -UseCheckpointSupervisor -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Python 'C:/Users/minle/.codex/worktrees/issue-5/StoneBench/app/controller/.runtime/test-venv/Scripts/python.exe' -ServerCacheSource 'C:/Users/minle/Documents/projets/StoneBench/app/prototype-transition/.runtime/server-cache' -BaseMcpPort 19565 -BaseGamePort 26381
$env:STONEBENCH_SPRINT_EVIDENCE='app/controller/.runtime/measurements-sprint.json'
./scripts/test-server.ps1 -Suite tests/transition_sprint.py -AcceptEula -SkipBuild -TickExecution unit -SecondTickExecution sprint -InitialPreparationTicks 120 -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Python 'C:/Users/minle/.codex/worktrees/issue-5/StoneBench/app/controller/.runtime/test-venv/Scripts/python.exe' -ServerCacheSource 'C:/Users/minle/Documents/projets/StoneBench/app/prototype-transition/.runtime/server-cache' -BaseMcpPort 19565 -BaseGamePort 26381
& <contract-python> tests/measurements_replay.py app/controller/.runtime/measurements-reviewed.json
```

Measurement run uses working MCP 19565/19566, game 26381/26382 and owned copy MCP 19567/19568, game 26383/26384. Only test-owned processes are stopped. Export with `tests/measurements_archive.py` using the seven named launcher/check/replay logs in the root or ignored `app/controller/.runtime/history13`. Final logs are archived; local historical failed runs are retained in the ignored controller runtime. A relaunch without `-UseCheckpointSupervisor` was refused before mutation, then corrected; it is not the successful final proof.

## Limits and downstream contract

Normal timing is movement **start +2gt**, not observed completion +2gt; instant is start, short-pulse extension is start + proven 0..2gt received pulse. Native instant/0/1gt montages are not runtime-proven here; arithmetic is tested and unclassified/missing events stay indeterminate. Alpha instrumentation is bounded, not universal circuit necessity or unknown memory coverage. No community-record claim or fused score; nonconformant results retain diagnostics. Full #12's long scenario matrix was not repeated; focused real copy/preservation/cancellation and protocol/storage regressions cover this change.

For #14/#15: reuse asynchronous request/status/cancel, independent-copy lease/checkpoint hashes/rollback, per-transition 36000gt and derived 432000gt bound; no added global quota. Keep per-transition `measurements`, repeater summary objectives, direct diagnostic, timestamps, sources/gaps and `record_eligibility=not_verified`. Game ticks are separate from wall time. Cancellation and final working-world validation can revoke interpretation. No paid campaign executed or authorized by this delivery.
