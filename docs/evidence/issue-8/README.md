# Issue #8 real-server evidence

Functional code: `fa06b25536d1b03858222f86a48d118fddffd7e4`. The later evidence commit changes only tests/documentation and archives. Minecraft/Fabric versions are pinned in `app/controller/build.gradle`; runtime: Java 21.0.12, Python 3.12, MCP SDK 1.26.0. Two isolated dedicated servers use MCP ports 19065/19066 and game ports 25881/25882. Test duration: 997.356 seconds; both servers saved all dimensions and stopped gracefully.

The verified archive is 58,368,101 bytes: 38,853 artifact descriptors, 20,263,671 logical JSONL entries, 192 complete traces and 6,796 tick samples. There are 3,276 distinct raw artifact contents; identical bytes are shared by hash.

## Results

- **160 successful vanilla MCP cycles:** 72 original cycles (four fixtures × lever/stone/oak × direct/repeater × three repeats), plus 88 cycles for the other eleven retained wood buttons (four fixtures × two modes). All twelve wood button types are exercised, rather than inferred from oak.
- Four fixtures: wall torch, repeater delay 1, repeater delay 4, torch/wire/sticky-piston mechanism. Every cycle checks frozen adapter preparation, natural interactions/releases, received signal, circuit timing, stable endpoints and queues.
- Each endpoint comparison covers **220 construction coordinates**, including air, the complete piston travel path and typed chest NBT/inventory (seven diamonds). Initial/closed states match exactly; direct/repeater opened and closed states match; three base repetitions agree. These are deliberately scoped behavioral comparisons. Absolute clocks, raw queues and raw traces remain intact; no exact-trace equality is claimed across different absolute start times.
- Four lateral faces pass. Pressing for one tick then `advance(24)` observes natural stone-button release. Re-pressing an active button and activating after support removal are refused without ticks/mutation.
- Eight archived negative controls: up/down, wrong adjacency, exact inventory divergence, blocked adapter footprint, interior surface, observer construction disturbed by adapter placement, and adapter floor below build limits. Observer disturbance reports an **infrastructure failure with mutation and exact differences**, never a successful preparation.
- `inputChecks` verifies semantic nested partition comparison with different artifact UUIDs, a real construction difference and corrupt adapter artifact rejection. `observationChecks` and targeted `streamingChecks` passed; the final build reruns input/observation checks, skipping the already validated streaming task after only input validation guards changed.

Observed edge intervals below subtract recorded simulation indexes. Source interaction occurs in `before_world_time`; natural button release and repeater transitions occur in `scheduled_block_ticks`. The archive retains both clocks and phases, so these intervals do not imply identical within-tick instants.

| Measurement | Direct | Real delay-1 adapter |
|---|---:|---:|
| Torch (including piston fixture) / repeater-1 input-to-first-component ON | 1 | 2 |
| Repeater-4 input-to-component ON | 7 | 8 |
| Stone button source / received pulse | 19 / 19 | 19 / 20 |
| Each wood button source / received pulse | 29 / 29 | 29 / 30 |

In the piston fixture, this interval measures the driving wall torch. The complete piston travel path is checked through its states and recorded events; the table does not claim piston movement starts at that same interval.

## Reproduce and verify

Run from the repository with a read-only MCP SDK interpreter and disposable server cache:

```powershell
$env:JAVA_HOME='C:\Program Files\Java\jdk-21.0.12'
$env:GRADLE_USER_HOME=Join-Path (Get-Location) 'app/controller/.runtime/gradle-home'
gradle.bat -p app/controller build -x streamingChecks --no-daemon --console=plain --offline
scripts/test-server.ps1 -Suite tests/input.py -AcceptEula -SkipBuild -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Python <MCP-1.26.0-interpreter> -ServerCacheSource <read-only-server-cache> -BaseMcpPort 19065 -BaseGamePort 25881
python tests/input_archive.py docs/evidence/issue-8/input-evidence.zip
```

The original run root was `app/controller/.runtime/tests-e423a95c6096415ab0a0fd28e3af7254`. To export a new successful run, supply its full path in `STONEBENCH_INPUT_EVIDENCE_ROOT`, capture suite/build output in `.runtime/input-final-test.log` and `.runtime/input-final-build.log`, and run `tests/input_archive.py` without arguments. Existing completed evidence archives are immutable; choose another output target for another campaign.

`manifest.json` records the exact code commit, deployed controller JAR hash, ZIP hash, byte size and verified artifact/trace/sample counts. `input-evidence.zip` contains the deployed JARs, both complete StoneBench journals and all artifact metadata/content, server stdout/stderr, build/test logs and the detailed matrix summary. Artifact metadata keeps its original UUID filename; exact raw JSONL bytes are stored once under `artifacts/by-sha256/<sha256>.jsonl` per server. Resolve an artifact UUID through its unchanged `.jsonl.meta` SHA-256. This removes repeated storage, without changing observations or references. The verifier streams each distinct content, checks every artifact descriptor, checks metadata/hash/bytes/count/JSON, resolves every nested trace reference, checks tick/world/simulation continuity, checks disjoint exact adapter/construction partitions and validates phase ordering for all 160 cycles.

## Limits and downstream contract

This proves dedicated-server vanilla primitives on four fixed circuits. It does not certify a complete regular DOOR, a player's network interaction or arbitrary JVM memory. Observation coverage limitations remain explicit.

Repeater preparation requires an initially inactive source/received input and three vacant exterior coordinates. These are adapter preconditions, not construction conformity rules. Downstream geometry should inspect the original checkpoint/interface or the actual `driver` of an adapted copy.

`Inputs.declared()` / `describe_task.input` return the original device position, actual driver, construction input/support, cardinal orientation, wall face, validation status, mode and adapter positions. `Inputs.adapter(pos)` means ownership; `Inputs.expectedExternalEvent(pos)` means only a candidate natural button/repeater callback, which rest diagnostics must match against scheduled type and actual state. Full raw observations include queues; `adapter_blocks` and `construction_blocks` preserve the exact same sample records separately. See [input contract](../../input.md).