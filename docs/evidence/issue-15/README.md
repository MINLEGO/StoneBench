# Issue #15 preparation evidence

No paid inference or credential read was performed. The only network reads were public OpenRouter model/endpoint metadata; the actual OpenRouter/SDK tests used a fake key and offline HTTP transport. The only auxiliary agent was GPT-6 Luna Max, read-only provider/source review; implementation used the requested GPT-6.1 Sol Medium.

## Final real Minecraft/Inspect/MCP rehearsal

Command from the isolated issue-15 worktree:

```powershell
& app/campaign/.runtime/venv/Scripts/python.exe -m app.campaign.launch rehearsal --output app/campaign/.runtime/rehearsal-v7
```

All eight independent task lifecycles exited 0. Seven explicitly submitted an immutable incomplete checkpoint; their verifier result remains `indeterminate`, with nullable exact volume. The last task (`5x5-speed`) retains `no_submission`, its checkpoint/inventory and diagnostics. These are infrastructure/isolation tests with scripted model usage, not successful doors, paid model performance or provider calibration.

[rehearsal-validation.json](rehearsal-validation.json) records exact identities/directories, native call counts, actual initial preparation ticks, zero useful initial ticks, result/verdict and context estimates for every task. All eight production MCP catalogues match and contain no test-only tool. Every frame and residue coordinate starts air; input, inventory, checkpoints and scheduled/block-event queues start empty. Each previous attempt leaves a chest with seven diamonds, declared input, advanced clocks and a checkpoint. Fresh absolute clocks equal only their own declared initial preparation count; no clock, state or queue was normalized to fabricate equality.

Measured context forecasts range **28,575..84,594 UTF-8 bytes**, including the actual MCP schemas and retained responses. This is offline context calibration only, not provider token/hidden-template calibration. The 32,768-token reserve margin and 65,536 final completion allowance remain provisional until the authorized provider calibration.

[rehearsal.tar.xz](rehearsal.tar.xz) contains 2,681 hash-inventoried payloads: frozen code/tests/docs and controller JAR, prompts/config/budgets, all native Inspect logs, source/copy worlds, settings, checkpoints, raw traces, operation journals, full tool results and verification reports. Immutable copied dependencies have deployed SHA-256 inventories; runtime libraries/cache trees are excluded. [archive-manifest.json](archive-manifest.json) lists every payload. [archive-check.json](archive-check.json) confirms the whole archive and every payload were read back; archive SHA-256: `448a949fdf4c14e702892e53bd2ce2ac366502bed756cd921c9af2573b9241ec`. [rehearsal-check.py](rehearsal-check.py) verifies reset, identities, explicit selection and actual source-byte equality.

Failed/debug runs v2..v6 remain exported under `preparatory-failures/`. They include a version preflight failure, an overly strict initial-zero-clock assertion (actual chunks needed declared preparation), a legitimate `read_blocks` refusal across an unprepared chunk, the scripted-provider ToolInfo mismatch, and old two-journal-only CLI/lifecycle mismatches. Source changes intentionally revoked comparison in those interrupted runs; their archives retain the source they tested. The final v7 is complete and its tested source bytes match the delivered implementation.

## Focused checks

- Offline controller build passed with JDK 21.0.12 and independent Gradle cache, seeded read-only from issue #7.
- Eight campaign boundary tests passed; six existing budget tests and four existing native Inspect tests passed.
- Two real Inspect/OpenRouter/OpenAI SDK tests passed under offline HTTP transport: exact endpoint routing, `reasoning.enabled=true`, real parser usage (200 input +100 completion =300 total, with 90 reasoning already inside completion), raw cost retention, no fake secret in logs, and context refusal before any provider request.
- [provider-validation-tests.json](provider-validation-tests.json): one accepted fixture and five rejected provider/cost/usage/overshoot controls. [paid-gate-tests.json](paid-gate-tests.json): absent authorization, absent calibration and rejected calibration all fail before a process/output/key-loader can start; the fake authorization fixture was temporary and deleted.
- The final eight single journals passed real clock accounting; two independent journals passed, and duplicating the same attempt journal was rejected.

The SDK runtime is pinned to Inspect 0.3.278, MCP 1.26.0 and OpenAI 3.29.0 (Inspect actually requires OpenAI >=3.4.0). `sdk-config.json` confirms SDK retries zero and reasoning enabled without inference. Controller/protocol/timing/volume code remains unchanged. Existing #14 defaults and test-only two-server behavior are preserved.

## Numerical paid gate, still pending

The full nonsecret proposal/hash is in [provisional-plan.json](provisional-plan.json); operational details and executable commands are in [campaign.md](../../campaign.md). Each attempt: total 2,000,000 tokens; construction completion 32,768; final completion 65,536 =8,192 visible +57,344 reasoning allowance; margin 32,768 plus recalculated actual context forecast. Request client guard: 524,288 context bytes. Stop immediately after the first missing-usage response, then suspend later paid tasks; the original standalone harness finite fallback remains unchanged.

OpenRouter model `xiaomi/mimo-v2.6-flash`: exact `makora/fp8` primary and `xiaomi/fp8` explicitly ordered fallback only; `allow_fallbacks=false`, exact `only` allowlist and FP8 quantization. All inference/sample/SDK retries are disabled. No effort or reasoning.max_tokens is invented. Real provider identity/cost/usage/completion bounds must pass calibration; length termination without usable visible/tool output blocks the eight tasks.

Price snapshot: input $0.13/M Makora or $0.14/M Xiaomi; completion $0.28/M (reasoning included); no cache discount assumed. At 80% input/20% completion: $2.56 or $2.688 for eight tasks. Worst nominal 16M-token split: **$4.48**. With one deliberately loose 1,114,112-token in-flight excess per attempt: **$6.97561088**, plus nominal 400,000-token two-call calibration **$0.112**, giving **$7.08761088**, conditional on provider limits/prices. This is not a hard monetary cap; hidden overhead/provider violations invalidate that bound. Calibration's own in-flight overshoot remains a limitation, rather than a guaranteed <=400k bill.

No authorization JSON exists from preparation and no real key was inspected. The loader reads only the primary gitignored secret file in the inference process after the paid gate; ambient keys never reach the Minecraft JVM/supervisor. Calibration must be explicitly authorized separately and accepted for this plan before any eight-task paid run. Issue #15 and parent #4 remain open until the real campaign and archive are complete.
