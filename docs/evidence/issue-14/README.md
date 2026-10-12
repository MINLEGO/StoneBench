# Issue #14 baseline evidence

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

Mock usage and reserve numbers are controlled, not measurements of a paid provider. The evidence does not prove model solving quality, real tokenizer/hidden input calibration or provider reasoning/routing behavior. #15 must present the numerical campaign budget and cost before any paid inference. #13's new measurement contract will be revalidated after its integration; this archive identifies its baseline explicitly.