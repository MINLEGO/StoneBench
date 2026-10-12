# Inspect harness

Issue #14 uses Inspect's native `react()` loop. A single-call Agent model adapter checks the phase/budget then delegates generation to Inspect's `Model.generate`; it never implements an inference loop. MCP tools retain their discovered schemas and descriptions, wrapped at the local execution boundary. An irreversible per-attempt phase object governs the wrapper, independently of Minecraft restoration/context and verification copies. Unknown tool names are excluded from the production allowlist.

Planned integration seam: no Controller/McpHttp change is needed. Existing MCP calls `list_checkpoints`, `verify_checkpoint`, `verification_status`, `cancel_verification`, and immutable evidence support explicit selection and independent-copy scoring. `submit_checkpoint(checkpoint_id)` is a harness tool, not a world operation. It validates existence before retaining the exact ID; the scorer verifies only that ID, never saves the current state or chooses a different checkpoint. No choice yields `no_submission`.

## Primary references verified 2026-10-12

- [Native ReAct agent, model Agent seam and continuation](https://inspect.aisi.org.uk/react-agent.html).
- [Native MCP connections and local execution](https://inspect.aisi.org.uk/tools-mcp.html).
- [ModelUsage including cached input, completion reasoning and cost](https://inspect.aisi.org.uk/reference/inspect_ai.model.html).

Inspect is pinned to 0.3.278, MCP SDK to 1.26.0. Provider usage is authoritative: `total_tokens` includes input and output; reasoning is part of completion and is never added again. A missing usage result poisons total availability for the whole attempt; the known subtotal remains separately labelled. Missing optional reasoning/cache/cost fields remain null. Inspect also records its own usage/events and token limit. The adapter's ledger attributes each reported call to construction/finalization and preserves provider totals without fabricating zero usage.

## Reserve and calibration

Configuration requires total budget, construction completion bound, final visible-output allowance, final reasoning allowance, margin and final-call safety count. Final completion bound = visible output + reasoning allowance, since the provider counts both as completion. No provider-specific reasoning effort/max_tokens field is inferred from model advertising. Preserve provider reasoning behavior; paid provider calibration belongs to #15 and needs user authorization.

Before generation, forecast one construction call = current context estimate + construction completion bound. Final reserve = estimated context of the last call + final visible output + counted reasoning allowance + margin. If used + forecast + reserve would exceed total, switch before that construction call and explicitly request an existing checkpoint ID. The forecast is an estimate, not paid usage. It includes messages and tool schemas, and uses UTF-8 byte count as a conservative text heuristic with documented overhead/margin; model/provider chat templates, hidden tokens, image inputs and unknown tokenizer behavior require actual calibration. Alpha text-only input is enforced. Record estimate, actual usage and estimate/actual difference per call so #15 can calibrate with the precise model/provider rather than a fake universal token guarantee.

Finalization tool calls can expand the next input context; recalculate before every call. Completion outputs are bounded through Inspect GenerateConfig `max_tokens`, including reasoning. Already running provider calls cannot be stopped at an exact total; record observed overshoot and then stop generation. The first missing usage triggers finalization and a finite final-call cap, while used/remaining totals remain unavailable.

Preparation status: modules only, actual native Inspect and real MCP scenarios still required before delivery. No inference paid campaign authorized or executed.
