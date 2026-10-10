# Issue #6 — construction MCP tests

tests/construction.py reuses the SDK 1.26.0 connection and structured-call helpers from tests/integration.py. It expects two fresh Minecraft servers with start_attempt available, as in the existing runtime harness.

The suite covers the block catalog; configurable versus computed state; explicit notification behavior; validation before mutation; duplicate positions and the 256-placement boundary; block and inventory readback; rejection of powered, locked, cooldown, raw-NBT, invalid-item, invalid-count, and invalid-slot input; unsupported components; and clock invariants.

The positive redstone fixture submits a three-wire dust line, its support blocks, and two nonadjacent chests with different inventories in one deliberately non-spatial batch. It checks vanilla east/west wire connections, both inventories before the first comparator callback, submitted notification order, callback root order, and callback observations that all requested blocks, properties, and inventories are present. It also checks the issue #2 negative regression by forcing a default-state wire dot, reading its four none connections, and repairing it through vanilla placement state. Same-block repeater changes use notifications; chest inventory replacement, chest-to-stone replacement, and chest-to-air deletion are read back.

A test-only fault forces an error after a chest and its inventory have been installed but before callbacks. The test checks the mutated error envelope, actual block/inventory state, recovery guidance, and a following repair lot. It also checks that synchronous chunk-scope expansion changes no clock, that invalid advances of 0 and 6001 ticks do not mutate the world, that one-tick and concurrent one-plus-twenty-tick advances update counters exactly, that the server stays frozen over a one-second wall-clock pause, and that a readiness loss after one executed tick reports the partial counter and can be restored without additional simulation ticks.

## Run

With both fresh servers listening on the configured MCP ports and the pinned Python dependencies installed:

    $env:STONEBENCH_MCP_PORTS = "18765,18766"
    .\scripts\test-server.ps1 -AcceptEula -Suite tests/construction.py

Or, with two fresh servers already running:

    python tests/construction.py

Final execution: the expanded suite, including the comparator notification regression, passed on Minecraft 1.21.11 in 21.951 seconds. The old jar fails the new regression after the unrelated stone placement. See README.md, runtime.log, comparator-negative.log and the hashed JSONL journals for scope and evidence.
