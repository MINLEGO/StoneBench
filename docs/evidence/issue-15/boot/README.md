# Zero-inference cached production boot

The first authorized `2x2-volume` launch failed before `run_attempt`/provider calls: each fresh runtime omitted Fabric's generated launch JAR, so the outer installer requested `meta.fabricmc.net/v2/versions/loader/1.21.11/0.19.5/server/json`; Java rejected that TLS chain with PKIX certificate_unknown. Its [immutable failure archive](first-paid-startup-failure.tar.xz) has SHA-256 `1fde7f892a2a7a2cec31c082f79d3a08a3ca4e3769cf99a0e02089d5eb1bb957`. Zero inference was used; the one-task authorization is not expanded to the other seven.

The pinned outer launcher (`2b63d293be54c8f5484a242859cab841dcee38511e11b2f82e92211f19872d08`) bytecode checks `.fabric/server/fabric-loader-server-0.19.5-minecraft-1.21.11.jar` and all manifest libraries before returning cached LaunchData; without them it installs via metadata. The lifecycle now requires/copies that generated JAR when ServerCacheSource is supplied, beside the existing verified Minecraft JAR and independent libraries/versions. Optional remappedJars/processedMods are also independently copied. Each added file is SHA-256 checked against its read-only cache source. No world, inventory, clocks, checkpoints or operation state is copied from the seed; no TLS bypass, truststore or watchdog change is introduced.

Primary cache bytes copied and verified:

| Cache artifact | SHA-256 |
|---|---|
| Generated Fabric launch JAR (643 bytes) | acc662032e437667ab70038de34f05a20348e362f0e04e490a3774f23167e0d7 |
| Minecraft intermediary JAR | 941f851276906ff862b8fdeb7f785af7ba28e6f9e87bfcdb14d56c621b542123 |
| Processed MixinExtras 0.5.5 | 5da883dc4bfb16e4ceca3f16d8c4ad937bdfb1ce337ed5ba15472d4d81dd6242 |

The first two ZIP containers differ from the successful real calibration's generated ZIP hashes, but **every uncompressed entry matches** (2 entries in the generated launcher, 15102 in intermediary); processed MixinExtras is byte-identical. [boot-proof.json](boot-proof.json) records container/payload hashes, copy equality and final source hashes. This reuses the same pinned code payloads, not earlier world state.

Actual dry production startup passed with 22 production MCP tools and no test-only tool. It starts a fresh 2x2-volume task, describes it and takes a frozen snapshot: zero useful ticks, 22 explicit preparation ticks, empty input and scheduled/event queues. Operation journal validation passed. The first loader-only dry startup skipped installer/TLS failure but exceeded the unchanged 180s readiness deadline; its roughly five-minute startup gap's cold/host cause is unproven. Its logs/world and the successful full-cache dry startup remain archived. Successful logs show pinned Minecraft 1.21.11/Fabric 0.19.5/Java 21/StoneBench 0.1.0 and no installer/meta/PKIX messages. Network traffic was not separately monitored.

```powershell
pwsh -NoProfile -File scripts/test-server.ps1 -AcceptEula -SkipBuild -UseCheckpointSupervisor -ProductionServer -ServerCount 1 -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Python 'app/campaign/.runtime/venv/Scripts/python.exe' -Suite tests/campaign_boot.py -ServerCacheSource 'C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache' -BaseMcpPort 19765 -BaseGamePort 26581
& app/campaign/.runtime/venv/Scripts/python.exe docs/evidence/issue-15/boot/check.py
```

[boot-preflight.tar.xz](boot-preflight.tar.xz) archives frozen current source/controller and both dry-run runtime worlds/logs, with immutable dependency caches excluded and their copied hashes retained. All 192 payloads pass offline readback; archive SHA-256 `d265baa5451633e3a25b3b7cb0575b19230ba92107cbbbe0374889bc87f07b1c`. The loader-only failed runtime predates the derived-cache copy lines; it is diagnostic failure evidence, not a final-source success claim. The successful suite/script bytes match the published archive and current checkout. Own lifecycle children were stopped; no foreign process was terminated. No key file was read and no model was created by the dry suite. Root may retry the already authorized single paid task in a new output after review; this implementation agent performs no paid retry.
