# Authorized two-call calibration and derived revalidation

Root executed exactly two user-authorized inference calls on 2026-10-12. No additional inference was made for the fix or replay. The eight-task paid campaign remains unauthorized. Plan hash stays `8758eb0f4d8b2a14c321bf161685103d4e0e88b135fada97b04abe293da2fc21`.

The immutable original [archive](original-calibration.tar.xz) has SHA-256 `c19c66dcb9ac0558bb6284c98bf7d6c69e40dfbfd3194a9f255a13c78572503e`; all 168 payloads are verified by the replay. Its status records calibration rejected because immediate metadata GET raised HTTPStatusError. That status and archive are not overwritten. The old validator did not retain HTTP status, so the initial failure's exact cause is unknown. Two later GET reads returned HTTP 200 using the same documented generation endpoint and IDs; only whitelisted fields and status are saved in [generation-reread.json](generation-reread.json), without headers, credentials or error bodies.

| Response ID | Input | Completion (includes reasoning) | Reasoning | Reported USD |
|---|---:|---:|---:|---:|
| gen-1791795598-tihCijiobt3VzJHqh78y | 3122 | 99 | 33 | 0.00043358 |
| gen-1791795599-MW8pxmzCZwe5EpZ1HamF | 6220 | 247 | 159 | 0.00087776 |
| Total | 9342 | 346 | 192 | **0.00131134** |

Both direct responses selected Makora, strategy direct, requested `xiaomi/mimo-v2.6-flash`, served version `xiaomi/mimo-v2.6-flash-20260921`, finish_reason tool_calls and valid tool output. Actual recorded request uses exact Makora/Xiaomi FP8 order/allowlist, reasoning enabled, max_tokens 65536, temperature 0, parallel calls false and no retries. FP8 identity is inferred from the exact provider allowlist and selected provider; metadata does not independently return a quantization tag. Later GET agrees on provider, version, cost, native input/completion/reasoning and finish reason. Cached input/write counts are zero. Inspect's model-level cost is not substituted for raw reported cost.

The current validator accepts documented direct routing metadata bound to the exact recorded model/provider request plus response usage.cost, or a valid later GET. Conflicting provider, generation identity, native token counts, reasoning or cost sources reject validation. Ambiguous selection, wrong model/provider/request binding and missing cost also reject. Token counts must be nonnegative integers excluding bool; known reasoning cannot exceed completion, and known cache counts cannot exceed input. Known GET native counts obey the same type/sign rules. HTTP status and resolved evidence source are retained.

[revalidation.json](revalidation.json) is a **separate derived offline result pending review**, not a new provider run or user authorization. [revalidate.py](revalidate.py) verifies archive payloads, original rejection, exact plan/budget/prompt/request configuration and actual tool response; then uses saved HTTP 200 metadata through MockTransport and the same current provider/calibration validators. It checks measured context forecasts 28576/39155 UTF-8 bytes against actual input 3122/6220 tokens and the 32768 margin. Reasoning 192 is included once inside completion 346. No inference or credential access occurs in replay.

```powershell
& app/campaign/.runtime/venv/Scripts/python.exe docs/evidence/issue-15/calibration/revalidate.py
& app/campaign/.runtime/venv/Scripts/python.exe tests/campaign_revalidation.py
```

Three focused tests cover real-response replay with GET unavailable and later available, plus eleven evidence-conflict mutations and twenty invalid-counter mutations. Counter fixtures include arithmetically consistent bool/negative input/completion/total, bool/negative/excess reasoning/cache and bool/negative GET native counts. Existing transport and launcher regression tests retain empty-length suspension. These two short read-only responses prove endpoint transport and observed accounting; they do not stress long reasoning, prove universal overhead bounds or solve any door. A later decision must authorize the eight tasks separately using the reviewed calibration and campaign forecast.

Primary sources checked: [chat completion metadata header and direct routing example](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion), [response usage.cost](https://openrouter.ai/docs/api_reference/overview), [generation metadata GET](https://openrouter.ai/docs/api/api-reference/generations/get-request-&-usage-metadata-for-a-generation). These document the evidence sources; the acceptance rule and FP8 mapping are StoneBench's explicit inference from the recorded request.
