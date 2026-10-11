# Issue #7 — recoverable observation evidence

Executed 2026-10-11 on Windows, JDK 21.0.12, Minecraft 1.21.11, Yarn 1.21.11+build.3, Fabric Loader 0.19.5, Python 3.12.9 and MCP SDK 1.26.0. Base: `1cf4749a4d69a800796c61c675f8954aa675271f` (issues #5/#6 merged). Final jar SHA-256: `C1B7AE5F969EE8EBEAA084C4605A12BBEB587FAF4929C33566E2465FE54E9599`. Source assertions execute during the offline build (`Observation checks passed`).

| Run | Real result | Jar provenance |
|---|---|---|
| `tests/observation.py` | PASS, 1 scenario suite, 15.589s; 76+12 serialized MCP operations | Final jar |
| #5 regression, full | PASS, 310.817s; server 1 reaches 6044 useful ticks, including one 6000-tick operation | `F7238783C51AF861918A4566004D108506E8BFF7A27707F3D2238A6446D7C06A`; run started before the final comparison-only diagnostic correction |
| #5 regression, final smoke | PASS, 10.743s; maximum operation 40 ticks | Final jar; full simulation/stepping/read hooks were unchanged by the subsequent comparison-only correction |
| #6 regression, final | PASS, 13.076s; 93+36 MCP operations | Final jar |
| Saved journals | PASS, independent `verify_journals.py` | Exact world-time deltas equal useful plus preparation ticks; every completed operation returns frozen |
| Saved artifact archives | PASS, `verify_observation_artifacts.py` | Every descriptor count, byte length and SHA-256 checked; full snapshot/event references reconstructed |

The 6000-tick run is a unit-step clock regression, not a trace-throughput measurement or sprint equivalence proof. Initial air-world preparation is variable and recorded separately. Region expansion/placement preparation inserted no world ticks. Owned servers all stopped cleanly; worlds, caches and jars remain local and ignored.

## Observed behavior and controls

The fixture places a south-facing observer whose north output controls an east-facing sticky piston and stone. After settling, a real vanilla neighboring block change schedules the observer. The following 12 explicit ticks contain 12 end-of-tick observations. The observer is powered at ticks 2 and 3, then returns unpowered; its final `powered` diff is absent. Six snapshots retain actual moving piston block entities, including a transient position beyond the initial push block, typed NBT and runtime progress/last-progress/absolute saved time. Event artifacts preserve actual state reads/writes, neighbor cascades, block schedule requests, callbacks, block-event enqueue requests and matching callbacks, with clocks, phases and both tick-local/full-operation order. Pending queues retain deadlines, priority and sub-tick order.

A 512-coordinate air region outside the initial/prototype rectangle is read through 29-entry pages, recovering every distinct coordinate while world/useful/preparation clocks remain unchanged. Invalid offsets, oversized pages and traversal ids are rejected. Inventories retain two occupied chest slots in typed NBT (`Items` list and byte `Slot` tags), and a hopper's long `last_tick_time` changes across successive ticks. A 7-to-8-diamond inventory mutation produces actual inventory/NBT differences; it is not normalized. Self-comparison of a complete trace reports equal; two complete traces with different epochs/lengths remain different at tick 1 with paginated fields while both individual continuity reports are complete.

Two independent negative server cases never become complete/equal: real forced-ticket removal stops a 40-tick request after 2 useful ticks and preserves only those 2 observations; a test-only vanilla scheduling request at (1120,80,1120), outside prepared chunks, is retained as an influence and marks coverage insufficient. Even an otherwise executed 1-tick trace remains incomplete after that gap. These are observation/infrastructure diagnostics, not failures of a door or conformity verdicts.

Pure production-helper checks detect byte/int and float/double type loss, exact long values beyond 2^53, compound key ordering, list ordering, inventory/temporal differences, first divergent tick/fields, omitted first/middle/last observations, absent state/queue/events, explicit incomplete flags and a truncated JSONL file failing its hash. No additional dependency/test engine was added; the assertion runner uses the cached game compile libraries.

`observations.json` holds the full MCP response summaries. `*-server-*.jsonl` are complete operation journals, including all page reads and controls. `*-artifacts.zip` preserve every referenced JSONL and metadata descriptor byte-for-byte, so the whole region, diff and trace can be recovered without the original live server. Extract with `Expand-Archive`, or read directly using Python's `zipfile`. `manifest.json` records all executed jar hashes and evidence hashes. The archives contain diagnostic JSON only, not game/world assets.

## Commands

From the dedicated issue-7 checkout:

```powershell
$java = 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe'
$python = 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe'
$seed = 'C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache'
scripts/build.ps1 -Java $java -Offline
scripts/test-server.ps1 -Suite tests/observation.py -AcceptEula -SkipBuild -Java $java -Python $python -ServerCacheSource $seed -BaseMcpPort 18965 -BaseGamePort 25781
scripts/test-server.ps1 -Suite tests/construction.py -AcceptEula -SkipBuild -Java $java -Python $python -ServerCacheSource $seed -BaseMcpPort 18967 -BaseGamePort 25783
scripts/test-server.ps1 -Suite tests/integration.py -AcceptEula -SkipBuild -Java $java -Python $python -ServerCacheSource $seed -BaseMcpPort 18969 -BaseGamePort 25785
$env:STONEBENCH_TEST_SMOKE = '1'
scripts/test-server.ps1 -Suite tests/integration.py -AcceptEula -SkipBuild -Java $java -Python $python -ServerCacheSource $seed -BaseMcpPort 18971 -BaseGamePort 25787
& $python tests/verify_journals.py docs/evidence/issue-7/observation-server-1.jsonl docs/evidence/issue-7/observation-server-2.jsonl
& $python tests/verify_journals.py docs/evidence/issue-7/regression-5-full-server-1.jsonl docs/evidence/issue-7/regression-5-full-server-2.jsonl
& $python tests/verify_journals.py docs/evidence/issue-7/regression-6-final-server-1.jsonl docs/evidence/issue-7/regression-6-final-server-2.jsonl
& $python tests/verify_observation_artifacts.py @(Get-ChildItem docs/evidence/issue-7/*-artifacts.zip | ForEach-Object FullName)
```

First isolated build seeded `-CacheSource C:\Users\minle\.codex\worktrees\issue-6\StoneBench\app\controller\.runtime -Offline`; seeds were copied read-only into this checkout. Test directories/ports are independent. The later comparison diagnostic change does not affect simulation/placement behavior; its final jar was rerun through #7, #5 smoke and #6.

## Limits retained

Coverage grows through actual vanilla reads/writes, queues and events, and preserves transient positions, but does not prove completeness for arbitrary components, direct chunk accesses, entities or all JVM memory. Every report keeps `certification=false` and block entities describe their runtime coverage. Hoppers are observed with their known runtime timestamps; rest/restoration remains indeterminate pending the subsequent proof. No fields are removed to force equality. No checkpoint, transition classifier, input adapter, conformity/volume evaluator, graphical client or Inspect campaign is claimed. Snapshot/trace storage may be expensive; pagination bounds entries rather than individual entry bytes, and no throughput guarantee is made.
