# Minecraft controller and MCP contract

Each attempt uses its own fresh server process and directory. Start two processes for two attempts; never reuse a world directory for a new attempt. `start_attempt` fails if that server already has an attempt. Its immutable `stonebench/attempt.json` records geometry, environment, preparation and identity. Every operation is appended to `stonebench/operations.jsonl`.

Production catalog: `start_attempt`, `describe_task`, `read_blocks`, `advance`. Streamable HTTP endpoint: `http://127.0.0.1:18765/mcp`. MCP protocol versions 2025-11-25, 2025-06-18 and 2025-03-26 are supported; initialization, notifications, tool discovery/calls and ping use JSON-RPC. Responses use JSON rather than the optional SSE stream; GET/DELETE return 405. Local Origin headers are validated. Server console logs are separate from MCP. See the [MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

```json
{"name":"start_attempt","arguments":{"task_id":"2x2-volume","budget_tokens":100000}}
{"name":"read_blocks","arguments":{"positions":[{"x":1024,"y":80,"z":1024}]}}
{"name":"advance","arguments":{"ticks":20}}
```

Task ids are `2x2`, `3x3`, `4x4`, `5x5` with `-volume` or `-speed`. Budget is caller supplied; omit it or use null when unavailable. It is not inferred to be zero. The immutable passage has origin (1024,80,1024), horizontal +X, vertical +Y, normal +Z; expected frame lists its coordinates. No blocks of physical encadrement are pre-built.

The initial ticking-ready chunk (64,64) covers an air region. It is an initial preparation scope, not a boundary of valid constructions. Reads outside prepared chunks return an explicit validation error. Reads are bounded to 256 coordinates, and callers must split larger requests; there is no silent truncation. `Controller.prepareChunks` is the server-thread extension seam for later placement/observation tools to expand the relevant set **before mutations**. Its preparation phase concludes only when every relevant chunk passes all three vanilla readiness checks. Later tools must resume their action after preparation; do not report placement success merely because preparation ended.

Operations enter a queue and all world access runs in `beforeTick`/`afterTick` on the server thread. An active operation owns the world until its result is recorded; concurrent requests wait. The vanilla tick manager advances one tick at a time at 20 TPS. No sprint acceleration is claimed. Preparation ticks and useful simulation ticks are separate. Readiness requires `shouldTickBlocksInChunk`, the ticking future, and a chunk level at least BLOCK_TICKING; a loaded chunk alone is insufficient. Loss of readiness revokes vanilla's already-computed tick permission, freezes the world and reports partial execution. An active operation has a 420-second infrastructure safety limit, separate from the requested 1..6000 ticks. Queue waiting does not consume this limit.

Each tool returns MCP `structuredContent` and equivalent text, with `operation_id`, `operation`, `attempt_id`, `phase`, `status`, `ticks_executed`, `simulation_ticks`, `preparation_ticks`, `world_time`, `frozen`, and `mutated`. Error kind is `validation` or `infrastructure` with a code and diagnostic. `mutated=true` means effects may have happened: a failed start needs a fresh process/directory, and a failed advance preserves its actual executed count. Disconnecting does not cancel an already accepted operation; consult the operation journal before retrying. Transport failure or process death does not fabricate a completed domain result.

Pinned environment: Minecraft 1.21.11, Yarn 1.21.11+build.3, Fabric Loader 0.19.5, Loom 1.14.10, Gradle 9.2.1, Java target 21. The launch scripts default to installed JDK 21.0.12. Seed 731928, flat air generator, no structures, no players, view/simulation distance 2, no automatic empty-server pause. Effective random tick speed 0, mob spawning false and weather advance false are set through vanilla rules and recorded. All eight tasks use these settings.

`-Dstonebench.test=true` adds isolated fixture/fault tools solely for disposable integration servers. They never appear in the production catalog. Removing forced chunk tickets exercises real readiness loss; no readiness boolean is mocked. Construction APIs, typed NBT/inventories, per-tick traces/diffs, checkpointing, conformity and Inspect are subsequent tickets; this controller does not claim those capabilities.
