# Issue #10 real checkpoint evidence

Validated on 12 October 2026, Java 21.0.12, Minecraft 1.21.11, Fabric loader 0.19.5, MCP Python SDK 1.26.0. The independent `codex/issue-10` worktree integrates validated dev `50940cb42083ac4e8bc8cde47a996a76bce52e7d`. Native sprint is the default, reusing issue #9's validated execution contract; unit remains an explicit reference option.

The delivered `scripts/checkpoint_server.py` owns each Java child, waits for the explicit HTTP acknowledgement, stops that child, verifies/stages/swaps the checkpoint and restarts frozen. This campaign uses that launcher, not a manual copy or an in-process reload. `--test` enables the original fixture only; production checkpoint/input tools retain their ordinary rules.

## Results

- Three restores of the older of two immutable checkpoint IDs each replay exactly **83 observations** against the original server's continuation: initial, lever on between ticks, 40 tick observations, lever off between ticks, 40 tick observations. Raw state, clocks, typed NBT, queues and inventories are compared without normalization. Only immutable artifact references are dereferenced to their recorded contents.
- Each loaded-state comparison is `equal` at `first_tick=0`, before any useful tick, with **zero preparation game ticks**. Chunks initially unready become ready while frozen. Preparation differences are retained as hashed artifacts; construction preservation is checked separately from readiness. The final comparison retains the readiness fields exactly.
- The current production lateral input API separately replays two 40-tick actions exactly, including events and absolute clocks. This is additional integration proof, not a claim that the floor fixture and production input have identical geometry.
- The seven-to-eight diamond negative control changes a copy of the first checkpoint proof observation through a guarded test-only tool, then invokes the production exact comparator. It reports `different`, tick 0, field `$.state.blocks.7,80,3.nbt.value.Items.value[0].value.count.value`. The immutable checkpoint itself is not edited. Actual persisted-file corruption is independently refused by storage verification.
- Real moving-piston capture and hopper-indeterminate capture are refused. Creation without established rest is refused. Checkpoint listing metadata remains exactly unchanged after every restore; historical trace contents remain readable through MCP. `session.lock` is excluded from checkpoint manifests and recreated in the live process.
- The full Java build passes checkpoint, geometry, streaming, rest, input and observation checks. Seven stopped-process Python controls pass: corrupt world/manifest, unsafe ID/foreign attempt, swap rollback, startup rollback, crash between directory moves and crash after durable marker before request archival. The last crash is recovered idempotently without applying a UUID twice. These injected filesystem tests do not claim Minecraft crash fidelity or power-loss durability.

`result.json` contains compact exact results and restoration diagnostics. `runtime.zip` exports the full 83-observation reference, full summary, immutable checkpoints (world/context/state/manifests), raw artifacts, operation journals, restoration/transaction records, server properties and per-boot logs. Old-world backups remain in the isolated test root; they are not duplicated in the compact export. `manifest.json` hashes the exports, tested source files and controller JAR. `build.txt`, `storage-tests.txt` and `minecraft-tests.txt` contain executed command output.

## Reproduce

From the worktree, PowerShell 7 (own ports/worlds/caches; source caches read only):

```powershell
$java = 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe'
$sdk = 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe'
./scripts/build.ps1 -Java $java -CacheSource C:\Users\minle\.codex\worktrees\issue-7\StoneBench\app\controller\.runtime -Offline
& $sdk tests/checkpoint_storage.py
$env:STONEBENCH_CHECKPOINT_EVIDENCE = "$PWD/app/controller/.runtime/checkpoint-summary.json"
./scripts/test-server.ps1 -Suite tests/checkpoint.py -UseCheckpointSupervisor -AcceptEula -SkipBuild -Java $java -Python $sdk -ServerCacheSource C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache -BaseMcpPort 19365 -BaseGamePort 26181
```

Game ticks and wall time are distinct: game clocks/counters are part of exact fidelity; real restart/test durations and per-operation `execution.wall_seconds` are diagnostic measurements. A restore deliberately rewinds the attempt's clock and counters, while previous journal rows remain immutable. The journal verifier checks each explicit restore segment and its requested clock/identity rather than assuming a globally monotonic clock.

## Scope and limits

The immutable prototype #3 source is `7bcdf3daaab752eef6d3f14011427c30c62f0e51`. Its preserved fixture has floor lever `(1,80,1)`, delay-2 repeater `(2,80,1)`, east-facing sticky piston `(3,80,1)`, stone `(4,80,1)`, seven-diamond chest `(7,80,3)` and stone floor `0..9 × 79 × 0..5`. The three replays compare against this campaign's original continuation; additional production observation instrumentation means no claim of identity with the old prototype report's serialization hash.

This proves the covered static chest/lever/repeater/piston mechanism and separate production input replay. It does not capture all JVM memory. Hopper timing, torch burnout, entity mechanisms and arbitrary block-entity memory are rejected or remain outside coverage. RNG streams, global scheduler counters, neighbor stacks and block-event memory are inventoried in checkpoint provenance; empty pending work/no players plus exact replay are bounded evidence, not universal certification. Door conformity is never a capture prerequisite. Staging/swap or startup failures preserve old-world backups/diagnostics; a loaded-state divergence remains frozen and blocks useful simulation. See [the production contract](../../checkpoints.md).
