# Issue #9 evidence

All live runs used Minecraft 1.21.11 / Yarn build.3, real dedicated servers and MCP. The final backend defaults to native sprint; the game-tick unit and API bounds remain exact.

| Check | Result | Evidence |
| --- | --- | --- |
| Unit reference observer clock | 36000 actual ticks, limit reached, 1804.562 seconds | full-summary.json, full-verification.json, full-test.txt |
| Final default sprint observer clock | 36000 actual ticks, limit reached, 78.4253275 seconds (459.035 measured TPS) | accelerated-summary.json, accelerated-verification.json, accelerated-test.txt |
| Unit versus native sprint | 56 exact comparisons, six native input cycles, PASS | sprint-equivalence.json, sprint-equivalence-test.txt |
| Controller regression | Ordinary 6000 bound, concurrency, journals, PASS | controller-regression-test.txt |
| Observation regression | Typed NBT/runtime, mobile pistons, inventories, artifacts, partial coverage, PASS | observation-summary.json, observation-regression-test.txt |
| Build and pure checks | Controller/input/observation/artifact/rest checks PASS | final-build.txt |

The chain's last movement is tick 26 and recognition is tick 27. Hoppers transfer at 8/16/24 and expire cooldown at 32; empty and locked inactive hoppers remain indeterminate because the effect and faithful resumption of lastTickTime are unproved. Pending future work and mobile pistons never produce positive rest. Missing coverage stays indeterminate; unavailable chunks are infrastructure failure. Real external button/repeater callbacks are distinguished by captured type and state; a wrong-type callback at the adapter stays internal.

The differential pilot starts both fresh worlds with 120 real empty-world preparation ticks, recorded separately from simulation, without clock resets. It compares absolute clocks, every block/NBT/inventory/runtime field, queue deadlines/priorities/order, input phases and events. Artifact UUIDs are resolved to original contents only for identity comparison; every original hash/count/byte length is verified. Operation events are reconstructed from each tick trace in exact order. Corrupt descriptor, false rest and truncated trace negative controls are rejected. The two full clock runs have different original preparation clocks; those values remain intact, and their duration comparison is not an assertion of equal initial absolute clocks.

The unit baseline completed unchanged before acceleration/storage updates. The pilot validates synchronous event streaming plus native sprint; the final default run and observation regression use that backend. build-provenance.json identifies each actual tested JAR SHA256. The final JAR is da5032885e61f135d82509cecb7f5cb9b98a42db1469061a4e059212c7ce1eed. sprint-bytecode.txt records the pinned native tick-manager implementation inspected for cached permission and sprint cleanup.

## Reproduction and immutable traces

Run scripts/build.ps1 -Offline, then scripts/test-server.ps1 -AcceptEula -Suite with the appropriate Python test script: tests/transition.py (full fixtures/36000), tests/transition_sprint.py (two modes), tests/integration.py or tests/observation.py. See docs/runtime-tests.md for Java/Python/cache/port arguments. The launcher accepts -TickExecution unit|sprint, default sprint; the differential test uses -SecondTickExecution sprint and -InitialPreparationTicks 120. The process deadline is 2400 seconds; HTTP and SDK reads allow 2450 seconds. These deadlines are separate from simulation bounds.

archive-manifest.json records SHA256, ZIP bytes and member counts. All five archives passed hash/count/CRC verification. Each contains the original server-N/stonebench artifact tree, metadata, journals and logs. Extract unit-artifacts.zip or accelerated-artifacts.zip to a fresh directory, then run:

    python tests/transition_evidence.py EXTRACTED_DIRECTORY docs/evidence/issue-9/full-summary.json
    python tests/transition_evidence.py EXTRACTED_DIRECTORY docs/evidence/issue-9/accelerated-summary.json

Use the corresponding archive for each command. Preparatory diagnostics remain under ignored local runtime storage. Source fixture authority is prototype #1 commit e3ef7f5e491e914690c472cfa6f149e8d3b3fe10: app/prototype-transition/RESULT.md, RESULT.json and src/main/java/stonebench/prototype/Experiment.java.

## Reuse and limits

advance, act_input and transition share the same queued controller backend. -Dstonebench.tickExecution=unit selects the reference; sprint is default. execution records mode/backend/game_ticks/wall_seconds/measured_tps/nominal_tick_rate, and environment.tick_execution records the selected mode. Freeze cancels sprint and stepping and clears cached tick permission. Checkpoint/verification callers must reuse this path and preserve original clocks/runtime, mode parameters and partial/error handling. No checkpoint restoration or arbitrary entity/mod equivalence is certified here; observed fixture rest retains certification=false.

Readonly reviewers: rest_review and sprint_research, both GPT-6 Luna Max. Initial coverage/no-op activity findings were corrected; final cadence and streaming lifecycle review reported no blocker. The parent performs final independent delivery review before merge. No merge or issue closure is part of this delivery.
