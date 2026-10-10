# Issue #5 — runtime evidence

Executed 2026-10-10 on Windows, JDK 21.0.12 / Python 3.12.9, with `tests/requirements.txt` (MCP SDK 1.26.0). Minecraft 1.21.11, Yarn 1.21.11+build.3, Loader 0.19.5, Loom 1.14.10, Gradle 9.2.1. No model API calls were used.

## Results and scope

| Criterion | Evidence |
|---|---|
| Dedicated empty isolated worlds | Two separate fresh directories/processes; distinct UUIDs; stone placed through test MCP only in server 1, air unchanged in server 2. |
| Task and actual block state | SDK asserts category, dimensions, integer passage, normal, frame, reference, separate objective, supplied budget and unknown budget null; reads actual air/stone. |
| Frozen exact advancement | Full journal advances 4+20+20+6000 useful ticks. World time 6055 = 6044 simulation + 11 preparation. Sleeps and subsequent reads preserve clocks. Invalid 0,6001,1.5,string,bool execute zero ticks. |
| Serialization | Concurrent SDK advances each execute 20 ticks; journal clocks grow by 20 then 20, with unique operation ids. All world access is server-thread guarded. |
| Ticking readiness | Initially chunk loaded=true but ready=false; start waits and logs preparation ticks. Actual forced tickets removed before advance produce infrastructure error at 0 ticks; removal during advance produces error after 1 actual tick. Sleeps after errors preserve clocks. Restoration prepares separately. |
| Honest reports | Operation, attempt, phase, errors kind/code, effective world/simulation/preparation clocks, mutated/frozen retained in JSONL. Before-start attempt id and unavailable budget remain null. |
| Reproducible pinned runtime | SHA-256 jars below, exact Python dependency pins, source build pins, copied Mojang jars SHA-1 checked against version metadata. |

`full/` is the first complete temporal scenario. All domain assertions passed, including the 6000-tick call, but the original harness exited with an AnyIO cancellation-scope error in `asyncTearDown`. That client bug was fixed by entering and closing MCP contexts in the same test task. The journal clock verifier passes independently for every full operation.

`final/` is the final jar with the corrected client harness: `Ran 1 test ... OK`, all contract/readiness/isolation/concurrency checks, 40-tick final advance, and independent journal clock verification. Final useful clocks: 84 and 1; preparation clocks: 7 and 12; world clocks: 91 and 13. The only production-code difference between these two jars is `GsonBuilder.serializeNulls()` in Controller and McpHttp; tick, freeze, queue and readiness logic did not change. The 6000 test was not repeated after this serialization-only correction.

- Full jar SHA-256: `3F37117CDB5D023038D2A8900F22F481D0479CC29ADB02EF6B62347167A2A75E`
- Final jar SHA-256: `3BE40D76F7341495C2B402CCB2573C7E39430E1C5B46F16D7871923AE4ECDB0B`
- Mojang server SHA-1: `64bb6d763bed0a9f1d632ec347938594144943ed`
- Mojang client SHA-1: `ba2df812c2d12e0219c489c4cd9a5e1f0760f5bd`
- Gradle distribution SHA-256 and Fabric launcher SHA-256 are checked in scripts.

## Commands

```powershell
.\scripts\build.ps1 -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Offline
python -m venv app\controller\.runtime\test-venv
& app\controller\.runtime\test-venv\Scripts\python.exe -m pip install -r tests\requirements.txt
.\scripts\test-server.ps1 -AcceptEula -SkipBuild -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Python (Join-Path $PWD 'app/controller/.runtime/test-venv/Scripts/python.exe') -ServerCacheSource 'C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache'
# Final serialization/client regression only, separate ports:
$env:STONEBENCH_TEST_SMOKE='1'
.\scripts\test-server.ps1 -AcceptEula -SkipBuild -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Python (Join-Path $PWD 'app/controller/.runtime/test-venv/Scripts/python.exe') -ServerCacheSource 'C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache' -BaseMcpPort 18767 -BaseGamePort 25583
Remove-Item Env:\STONEBENCH_TEST_SMOKE
& app\controller\.runtime\test-venv\Scripts\python.exe tests/verify_journals.py docs/evidence/issue-5/full/server-1.jsonl docs/evidence/issue-5/full/server-2.jsonl
```

All four owned servers stopped cleanly; worlds/jars stay local and ignored. Production catalog exclusion of test tools is checked statically via the `Controller.TEST` guard (default false); no third production-mode server was booted. This issue does not validate sprint, placement catalogue, NBT, checkpoint fidelity, door conformity, or Inspect orchestration.
