# Issue #14 evidence
## Integrated #13 validation

`origin/dev` #13 (`19135a2b2a338dfc678df76a7e501b4a1f756e68`) was merged without conflict in `3dced006af05185591af0a247a32f3331df6001b`. The harness execution module is unchanged from reviewed head `de7ee797269718240b8fd5818ab501433322728a`; only the actual MCP test gains final-measurement assertions, and documentation/evidence are updated.

[inspect-mcp-integrated13.tar.xz](inspect-mcp-integrated13.tar.xz) and [validation-integrated13.json](validation-integrated13.json) identify the current complete run, exact tested source bytes, new built/deployed JAR and archive hashes. The archive includes native Inspect logs, full source/copy journals and retained artifacts/reports, checkpoint manifests/contexts/states, updated source snapshots (harness/controller/measurement worker) and validation outputs. [proof-check-integrated13.txt](proof-check-integrated13.txt) verifies every archived payload against the inventory and compares archived tested source bytes to the worktree.

- New offline build passed in 87 s; 4 native Inspect tests passed in 8.7 s, and all 6 budget tests passed.
- Complete actual Minecraft/Inspect/MCP suite passed in 417.823 s: all 8 scripted scenarios and cold initialization. The two common journal checks also passed: source 782 operations / 9 simulation ticks / 10 preparation ticks / world time 19; cold server 2 operations / 0 simulation ticks / 20 preparation ticks / world time 20. These are the actual reported clocks, including preparation, with no normalization.
- Final scorer metadata retains the full measurement object unchanged. Canonical dynamic_volume remains indeterminate, value=null, with differing minimum/maximum envelopes and explicit gaps. Its observed high bound is not promoted to an exact volume. Repeater opening/closing remain 6 game ticks; direct diagnostic transitions remain 4 game ticks, preserving interaction, signal, movement and rest provenance. objectives_combined=false and no fused score is introduced.
- Explicit old ID selection, valid/invalid world-tool refusals, restore attempts during copies, source conservation, selection during an active copy, cancellation, invalid/no submission, unavailable usage, long reasoning and observed overshoot all pass again on the new controller. No common source was directly edited and no paid inference occurred.

The original #12 artifacts below are historical baseline evidence. Current runtime source hashes are those inside the integrated archive/validation file, rather than the older source snapshot. Paid provider calibration and reasoning/routing behavior remain unverified as described below.

Inspect 0.3.278 and MCP SDK 1.26.0, Python 3.12, Java 21.0.12, Minecraft 1.21.11. Controller baseline: dev `71c0f239c73bf15a9292e01c1fae3e6596b66f05` (#5–#12). Harness source before final test-only/document changes: `c7d0b1931a06656d5ec3d95a5c30afe4274cff35`; exact source/JAR/archive hashes are in [validation.json](validation.json). No shared controller or launcher source was modified. [harness-source-and-tests.zip](harness-source-and-tests.zip) preserves exact runtime source bytes and updated native test outputs; [source-validation.json](source-validation.json) hashes that snapshot. After the full MCP run, a provider-failure exception path was added and verified with native Inspect: an unsuccessful call without usage now remains unavailable, while its exception is propagated. Normal MCP execution paths are unchanged.

[inspect-mcp-baseline12.tar.xz](inspect-mcp-baseline12.tar.xz) contains native Inspect JSON logs (including full messages/tool errors/usage), per-attempt prompt/catalogue/config/budget/results/events and full retained MCP responses, source/copy operation journals and artifacts, verification reports/status/worker logs, checkpoint contexts/states/manifests, test/build outputs and a SHA-256 inventory. Entries preserve each server's directory structure. Absolute runtime paths in reports map to `servers/server-N/` in the archive. Worlds and dependency binaries are omitted; their checkpoint hashes remain in manifests and the worlds remain in the local disposable test root. This is an evidence archive, not a playable-world distribution.

## Results

- Offline build succeeded, including controller's existing Java checks.
- Six budget tests and four native Inspect tests passed. Native token-limit recovery is tested against Inspect's own counter, including a completed 38,000-token call exceeding a 30,000 limit.
- Full Minecraft MCP suite passed with eight scripted scenarios plus cold harness initialization on a second server; both complete operation journals passed the common clock validator. The source had 593 operations, 9 simulation ticks and 9 preparation ticks; the fresh server had 2 operations, 0 simulation ticks and 4 preparation ticks. No operation errors in either source journal.
- During finalization, actual mutation/action/advance/restore tools are refused, including restoration attempts during copy verification. Full raw working snapshots and source operation names prove conservation during/after verification. Invalid arguments and unknown tools are rejected by native Inspect without reaching Minecraft.
- The explicitly submitted older checkpoint differs from both the newest checkpoint and the conforming reference. The scorer verifies that exact old ID and returns its nonconforming result. A separate submission during an active conforming copy waits for that job and verifies the selected ID afresh. Invalid or absent selection yields no_submission; no checkpoint is auto-selected.
- Copy cancellation produces infrastructure_error without changing the source. Missing model usage remains unavailable; final reasoning is charged as completion without duplication. Overrun scenarios preserve Inspect's real counts and stop the native loop.
- A mock API-key sentinel was present only in the test process environment. Export aborts if it occurs in any evidence payload; none occurred. No real key was accessed, copied or logged. No paid inference occurred.

## Reproduce

Use an isolated venv with app/harness/requirements.txt, then:

```powershell
& app/harness/.runtime/venv/Scripts/python.exe tests/harness_budget.py
& app/harness/.runtime/venv/Scripts/python.exe tests/harness_native.py
& scripts/build.ps1 -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -CacheSource C:/Users/minle/.codex/worktrees/issue-7/StoneBench/app/controller/.runtime -Offline
$env:STONEBENCH_HARNESS_EVIDENCE = Join-Path $PWD 'app/harness/.runtime/new-evidence'
$env:STONEBENCH_HARNESS_SUMMARY = Join-Path $PWD 'app/harness/.runtime/new-summary.json'
& scripts/test-server.ps1 -Suite tests/harness_inspect.py -AcceptEula -SkipBuild -UseCheckpointSupervisor -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Python (Join-Path $PWD 'app/harness/.runtime/venv/Scripts/python.exe') -CacheSource C:/Users/minle/.codex/worktrees/issue-7/StoneBench/app/controller/.runtime -ServerCacheSource C:/Users/minle/Documents/projets/StoneBench/app/prototype-transition/.runtime/server-cache -BaseMcpPort 19665 -BaseGamePort 26481
```

The final run uses disposable root `app/controller/.runtime/tests-99e68ed38275445c8f3ec5f9df204852`; worlds remain there. Native MCP/AnyIO emitted ResourceWarning messages about receive streams on closure, but all scenarios, journals and PID-scoped shutdown completed successfully. Earlier diagnostic runs exposed shared scripted-model caching and Inspect's pre-return limit behavior; both were corrected before this passing run.

Mock usage and reserve numbers are controlled, not measurements of a paid provider. The evidence does not prove model solving quality, real tokenizer/hidden input calibration or provider reasoning/routing behavior. #15 must present the numerical campaign budget and cost before any paid inference. The historical archive identifies its #12 baseline explicitly; the integration above separately validates the #13 measurement contract.