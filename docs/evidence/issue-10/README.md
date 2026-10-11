# Issue #10 preparation evidence

This is an integration gate, not completed checkpoint acceptance. No real checkpoint restore or 83-observation Minecraft replay has been executed yet. Common MCP/controller/launcher files remain reserved for issue #11 until its delivery.

Validated on 11 October 2026 in the independent `codex/issue-10` worktree, based on `bd32f911ac9a20e7f1ae98277588bebd03d3a451`:

- Standalone Java 21.0.12 `javac`/`CheckpointChecks` passed: exact tick-0 NBT field for seven-to-eight diamonds, tag-type and absolute-clock changes, equal incomplete state stays indeterminate, frozen-only/stale rest/hopper/torch/pending queues refused, two immutable IDs retained, process lock excluded, corrupt world and foreign attempt rejected. This is pure logic/filesystem evidence, not Minecraft fidelity proof.
- Python 3.12 `tests/checkpoint_storage.py`: five tests passed; staged swap preserves old world/history, world and manifest corruption refused, installation failure rolls back, boot rollback preserves failed-world evidence, unsafe IDs/foreign attempts refused. No Minecraft process runs in these stopped-process transaction tests.
- `python -m py_compile tests/checkpoint.py tests/checkpoint_storage.py tests/checkpoint_supervisor.py` passed. The MCP suite is prepared for the original-server continuation/three restores/83 observations and a separate current production input replay, but not yet wired or run.
- `scripts/build.ps1 -Java <JDK21> -CacheSource <issue7 runtime> -Offline`: full controller build passed in 2m21s, including input/observation/rest/streaming checks. New classes compiled; CheckpointChecks was invoked separately. The subsequent payload-field naming/root-symlink checks are covered by the next integration build.

Commands (PowerShell, from the worktree):

```powershell
$checkpointGson='C:\Users\minle\.codex\worktrees\issue-7\StoneBench\app\controller\.runtime\gradle-home\caches\modules-2\files-2.1\com.google.code.gson\gson\2.13.2\48b8230771e573b54ce6e867a9001e75977fe78e\gson-2.13.2.jar'
& 'C:\Program Files\Java\jdk-21.0.12\bin\javac.exe' -cp $checkpointGson -d app/controller/.runtime/checkpoint-pure app/controller/src/main/java/stonebench/ObservationComparison.java app/controller/src/main/java/stonebench/CheckpointComparison.java app/controller/src/main/java/stonebench/CheckpointStorage.java app/controller/src/main/java/stonebench/Checkpoints.java app/controller/src/test/java/stonebench/CheckpointChecks.java
& 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -cp "app/controller/.runtime/checkpoint-pure;$checkpointGson" stonebench.CheckpointChecks
& 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe' tests/checkpoint_storage.py
```

Prototype source: immutable #3 `7bcdf3daaab752eef6d3f14011427c30c62f0e51`. The fixture preserves floor lever `(1,80,1)`, delay-2 repeater `(2,80,1)`, east-facing sticky piston `(3,80,1)`, stone `(4,80,1)`, seven-diamond chest `(7,80,3)` and stone floor `0..9 × 79 × 0..5`. Its test-only between-tick toggles do not broaden the production lateral input API. No arbitrary JVM memory or motion-checkpoint guarantee. See `docs/checkpoints.md` for integration seams and remaining acceptance.
