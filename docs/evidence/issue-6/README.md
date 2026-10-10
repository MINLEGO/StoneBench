# Issue #6 — ordered construction evidence

Executed 2026-10-10 on Windows, Minecraft 1.21.11 / Yarn 1.21.11+build.3 / Fabric Loader 0.19.5, JDK 21.0.12, Python 3.12.9 and MCP SDK 1.26.0. Base: `effa00e5a4efd23578e3f45ae5888cf8a9581e7b` (issue #5). The pinned, isolated build passes; the final controller jar SHA-256 is `B388D85BBD4B118563F513F2DE50E7D43E585903B688FF06DF5017DFCB2F1BEE`. See `summary.json` for journal hashes and exact counters.

## Results

`tests/construction.py`: **PASS**, `Ran 1 test in 22.984s / OK`, through the real MCP SDK against two fresh dedicated Minecraft servers. `tests/verify_journals.py`: **PASS**, independently rerun against the saved copies here. Server 1 completed 93 operations, 27 simulation ticks and 20 preparation ticks (world time 47); server 2 completed 24 operations, no simulation ticks and 17 initial preparation ticks (world time 17). All owned servers stopped cleanly. Worlds and jars remain ignored locally; evidence contains only logs and JSONL records.

| Requirement | Actual evidence |
|---|---|
| Discover configurable versus computed state | 61 explicit supported ids; orientation, attachment face, repeater delay, comparator mode, inventories; wall attachment, comparator subtract mode and hopper inventory read back; power/lock, piston progression, cooldown, timestamps and queue injection rejected. Unsupported id is a distinct `unsupported_component` error, not a conformity restriction. |
| Whole-lot validation | A valid first placement followed by invalid locked-state input leaves both positions air; invalid slots/items/counts/NBT, duplicate positions, missing notification option and 257 placements leave blocks and clocks unchanged. A valid 256-placement lot succeeds without truncation. |
| Geometry/inventories before callbacks | Dust appears before its support in the submitted list; two separate chests have distinct inventories. Real state callback and neighbor/comparator hooks observe all geometry, configurable parameters and both inventories already installed. Root indexes are nondecreasing and notifications follow submitted coordinates; cascades remain within their root. Inventory `setStack/markDirty` comparator calls are deferred during installation. |
| Correct vanilla placement | Dust reads `east=side,west=side,north=none,south=none` across the line. The test-only raw default state produces a dot; the same predicate rejects it, and a normal lot repairs it using vanilla placement. This retains the issue #2 placement failure rather than silently adopting its artificial default. |
| Neighbors determine functioning | A sticky piston is submitted first, its push block next and its redstone source last. It stays unextended while frozen, then extends and moves the stone after four explicit vanilla ticks; no powered state or event is injected. |
| Actual readback/replacement | Exact inventories read after installation; same repeater gets new facing/delay with a real added-state callback. A replacement inventory clears previous slots. Chest → stone → air removes the inventory and block entity. |
| Honest partial effects | A test-only fault after complete geometry/inventory installation returns infrastructure error, `mutated=true`, frozen actual chest/inventory records and recovery guidance. A following valid lot repairs it. No rollback is claimed. |
| Frozen chunk extension and regression #5 | A lot crosses new distant chunks and resumes only when readiness is true, with world/preparation/simulation clocks unchanged. Null budget, invalid advances, exact useful ticks, serialized concurrent advances, frozen wall-clock pause and real readiness loss after one executed tick pass. |

## Commands

```powershell
.\scripts\build.ps1 -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -CacheSource 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime' -Offline
.\scripts\test-server.ps1 -AcceptEula -SkipBuild -Suite tests/construction.py -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Python 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe' -ServerCacheSource 'C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache' -BaseMcpPort 18865 -BaseGamePort 25681
& 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe' tests/verify_journals.py docs/evidence/issue-6/server-1.jsonl docs/evidence/issue-6/server-2.jsonl
```

The shared issue-5 cache/SDK was read only; the issue-6 cache and server roots are isolated. The initial cache seed exposed a missing root Loom Mojang version manifest; `build.ps1` now copies that manifest for reproducible offline cache seeding and still excludes lock files. Two earlier fresh runs stopped on incorrect test expectations (dust endpoint connection, then the existing #5 generic error code whose message starts `scope_unprepared`); the assertions were corrected to the observed engine/API contract, without changing production behavior. The second failed assertion log is retained. The final run uses the last compiled Java code and the corrected suite.

## Scope and contracts for #7

The engine evidence proves these fixtures on the pinned version, not every possible arrangement of the 61 supported block types. No whole-prototype branch was merged. Production test-tool exclusion remains guarded by `Controller.TEST` (default false); no third production-mode server was booted. The 6000-tick scenario from #5 was not repeated because ordinary stepping is unchanged; this run adds focused temporal/readiness regression.

`Controller.prepareChunks(chunks, continuation)` resumes an action after preparation while frozen; the continuation owns completion. New observation tools should use this overload. Construction and readback return actual block properties and inventory ids/counts. Typed internal block-entity fields, queues, per-tick traces/diffs, checkpoints and conformity remain subsequent work. Hopper memory is neither injectable nor certified restored. `notify_neighbors=false` deliberately suppresses callbacks and propagation, and item entities are not spilled by construction replacements. Coverage failures stay explicit and do not turn into hidden conformity rules.
