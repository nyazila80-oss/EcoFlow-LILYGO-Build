# AUDIT20.4.5 / 9.36.7.10 — WebUI + AsyncTCP + Heap + NimBLE stress audit

## Scope
Static review of the current `work9380` tree plus a deliberately adversarial host-side resource model. Focus: the coverage gap left by earlier lifetime simulations: simultaneous REST JSON construction, WebSocket allocation/churn, resident Wi-Fi/AsyncTCP/cloud pressure, and a PowerStream BLE worker on top of the shared NimBLE host.

## Source facts verified
- `/api/state` builds dynamic JSON with `String json; json.reserve(2048)` and performs Preferences reads inside the AsyncWebServer callback.
- `/api/bms` builds dynamic JSON with `String json; json.reserve(4096)` and records calls/inflight/build latency/min free heap/min largest 8-bit block.
- `/api/bms/full` uses another `reserve(4096)` path.
- WebSocket send paths use `makeBuffer()` and have fail-closed behavior if allocation fails.
- PowerStream BLE creates a 6144-byte worker after pre-admission and has a second runtime memory guard.
- PowerStream cloud creates a 6144-byte task pinned to core 1; once created its task lifetime is resident.
- CAN tasks are pinned and have explicit stacks: 2560, 2560, 3072, 4096 bytes; diagnostic heartbeat 2048 bytes.

## New stress model
`host_sim_web_async_heap_nimble_stress_93710.py` intentionally models fragmented free/largest-block envelopes rather than pretending to emulate ESP-IDF's allocator. It adds resident pressure, REST contiguous allocation demand, bounded WebSocket allocations, and PS-BLE worker/GATT/transient pressure. Current PS-BLE gates are represented as 18k free/9k largest pre-task and 9k free/6k largest runtime.

Result (500,000 randomized stressed states):
- invariant violations after passing runtime guard: **0**
- PS-BLE admitted: **65,972**
- runtime fail-closed aborts: **8,175**
- modeled REST contiguous-allocation failures: **26,646**
- modeled WebSocket fail-closed drops: **1,206**
- auth-only admitted cases: **42,998**
- full-command admitted cases: **22,974**
- median final largest block: **9,279 B**
- p10 final largest block: **3,392 B**
- median modeled free-vs-largest fragmentation gap: **10,442 B**

These counts are not hardware probabilities. The distributions are intentionally adversarial. They establish only that the current BLE two-stage gate is logically capable of failing closed while web allocations can independently become the first allocation victim under fragmented-heap pressure.

## FMEA delta
### F1 — REST allocation is first visible failure
Cause: total free heap remains nonzero but largest contiguous block is below a large JSON/String/transient demand.
Effect: `/api/bms`, `/api/bms/full`, or `/api/state` becomes slow/fails while heartbeat/Wi-Fi can remain alive.
Severity: medium/high for availability. Detectability: now good via `/api/net/health` (`bms_api_*`, min heap/largest) and serial heartbeat.
Mitigation: hardware A/B first; later replace dynamic concatenation with bounded/streamed serialization and snapshots.

### F2 — BLE passes precheck, then runtime pressure crosses threshold
Cause: 6144-byte worker plus NimBLE client/GATT/transients after admission.
Effect: operation aborts before command/auth continuation.
Severity: low/medium because fail-closed. Current mitigation: runtime 9k/6k guard. Model found 8,175 such aborts and zero post-guard modeled invariant failures.

### F3 — WebSocket allocation under pressure
Cause: fragmented largest block during churn/push.
Effect: dropped frame rather than second fallback allocation.
Severity: low/medium. Existing `makeBuffer()` fail-closed path is preferable to retry amplification.

### F4 — Cloud task residency reduces later margin
Cause: cloud task remains resident after first creation even when HeavyOp prevents simultaneous active cloud/PS-BLE work.
Effect: later C/D test has lower memory margin than fresh boot.
Severity: medium. Detect with A1/A2/C1/C2 test matrix.

### F5 — Async callback performs NVS and large String work
Cause: `/api/state` reads Preferences and builds response in callback context.
Effect: extra callback latency and transient allocations; not proven root cause.
Severity: medium. Architectural mitigation after diagnosis: immutable config snapshot for reads; deferred single-owner writes.

### F6 — Credential exposure in NO-WEB-AUTH diagnostic build
Cause: `/api/state` returns stored Wi-Fi/MQTT passwords while web Basic Auth is bypassed.
Effect: local-network credential disclosure.
Severity: high security, independent of crash root cause. Must be fixed before production release. Do not expose this diagnostic build to untrusted LANs.

## Root-cause interpretation
The new model closes the previous `web_pressure_events=0` coverage gap. It does **not** prove ESP32 heap fragmentation or AsyncTCP failure. It does show a coherent failure sequence consistent with the observed symptom: WebUI allocation can fail before the whole device fails, and PS-BLE/NimBLE can reduce margin without being the primary defect.

## Release gate
- Controlled bench/hardware diagnostic: **GO**, after clean compile/link succeeds locally.
- Production release: **NO-GO** until credential return from `/api/state` is removed and real-hardware web/heap evidence is collected.
- Do not add more speculative fixes to 9.36.7.10 before A1/A2/C1/C2/D evidence; changing the allocator behavior now would invalidate the diagnostic baseline.

## Required hardware evidence on first failure
Do not power-cycle immediately. Capture serial heartbeat; router association/IP; `/api/net/health` if reachable; `free heap`, `largest8`, `esp_min_free`; `bms_api_min_heap`, `bms_api_min_largest`, max inflight/build time; WebSocket client counts; Wi-Fi disconnect/lost-IP counters; PS-BLE stage/worker/heavy-owner. This separates HTTP allocation failure, network loss, loop/task failure, and BLE pressure.
