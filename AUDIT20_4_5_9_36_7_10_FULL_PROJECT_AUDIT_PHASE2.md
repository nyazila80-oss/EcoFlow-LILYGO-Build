# AUDIT20.4.5.9.36.7.10 — Full Project Audit Phase 2

## Scope
Second-pass static audit of the complete 9.36.7.10 project, focused on cross-subsystem resource ownership, secrets, AsyncWebServer callback behavior, heap fragmentation, task stack reservations, and diagnostic validity.

## High-severity finding: secrets returned by unauthenticated /api/state
`remoteAuthRequest()` has deliberately allowed all local WebUI/API requests since 9.36.4. `/api/state` currently opens NVS namespaces `net` and `mqtt`, reads Wi-Fi and MQTT passwords, and serializes both back into JSON (`wifi.pass`, `mqtt.pass`). `data/index.html` then repopulates the password fields from those values.

This is incompatible with the current NO-WEB-AUTH A/B design: any host that can reach port 80 can retrieve those stored secrets. This is independent of the GUI stability problem and should be corrected before treating 9.36.7.10 as a release candidate.

Recommended correction: make Wi-Fi and MQTT password fields write-only/keep-existing, never return them from status APIs, and avoid NVS password reads from GET callbacks. Preserve OTA Basic Auth.

## Heap/fragmentation finding
The highest-risk allocation sites remain `/api/state`, `/api/bms`, `/api/bms/full`, and the PowerStream BLE status JSON. They build large Arduino `String` objects through repeated concatenation. `reserve(2048)`/`reserve(4096)` reduces reallocations but does not make the route allocation-free; temporary `String` objects are still created for many numeric/boolean conversions and concatenations.

At the previously observed ~21 KiB free heap, Largest-8-bit block is the more diagnostic quantity than aggregate free heap. A request can fail or stress AsyncTCP even when total free heap looks acceptable if the largest contiguous block is too small.

## Async callback finding
`/api/state` performs Preferences/NVS reads directly inside an AsyncWebServer callback. `/api/net` also performs NVS comparison/read work in the callback before deferring application. These are not proven to cause the GUI hang, but they unnecessarily mix flash/NVS work with the network callback execution context. A future hardening pass should use main-loop-owned cached snapshots and queued writes.

## Static RAM / websocket budget
Two WebSocket rings reserve 4096 bytes each (8 KiB total) plus a 1025-byte static flush buffer. This memory is bounded and not a leak. `/bms` WS uses a fixed 160-byte stack JSON and `makeBuffer`; allocation failure is fail-closed. Therefore WS logging has a predictable baseline RAM cost, while REST JSON generation remains the more fragmentation-prone path.

## Task stack reservations
Application-created stacks include CAN log 2560, CAN alert 2560, CAN RX 3072, CAN decode 4096, diag heartbeat 2048, persistent PowerStream cloud worker 6144 after first creation, and transient PowerStream BLE worker 6144. These are in addition to Wi-Fi/LwIP/AsyncTCP/NimBLE system tasks and objects. The cloud worker is persistent once created, so a cloud API test can permanently lower the post-test heap reserve for the rest of the boot session.

## BLE coexistence interpretation
Historical stability of JK-BLE + JK app + WebUI argues against JK BLE itself being the root defect. Current BLE paths can still expose a marginal heap/scheduling condition because the modern project has more persistent tasks, diagnostics, web endpoints and shared BLE ownership state than the older stable builds.

## Authentication root-cause interpretation
HTTP Basic Auth is no longer executed by `remoteAuthRequest()`, so it cannot be a necessary cause of a GUI failure reproduced on 9.36.4+. Historical 401/retry and WebSocket auth churn remain plausible load amplifiers only. OTA auth remains active and separate.

## Dependency reproducibility
`ESPAsyncWebServer @ ^3.7.10` and the Espressif platform are not exactly pinned. A clean build on another date can therefore resolve different compatible versions. Do not change dependencies during the current hardware A/B investigation; first capture the actually resolved versions from the user's successful PlatformIO build. Then create a separate reproducibility-hardening change.

## FMEA priorities
1. Dynamic REST JSON + low Largest Block -> Web/AsyncTCP allocation failure or severe latency. Severity high, occurrence plausible, detectability improved by current diagnostics.
2. Persistent cloud-worker stack reduces reserve -> later BLE/Web pressure. Severity medium-high, occurrence conditional, detectable via before/after heap snapshots.
3. NVS work in Async callback -> callback latency/contention. Severity medium, occurrence routine for `/api/state`, not yet proven causal.
4. Wi-Fi/LwIP disconnect/recovery -> UI unreachable while application alive. Severity high, detectable with event counters/serial heartbeat.
5. NimBLE coexistence -> additional heap/task/radio pressure. Severity medium-high, but historical evidence lowers likelihood as standalone root cause.
6. Web Basic Auth -> historical load amplifier; not current necessary root cause.
7. Credential disclosure via `/api/state` in NO-AUTH build -> security severity high and confirmed statically; independent of GUI hang.

## Release-gate conclusion
9.36.7.10 is a diagnostic build, not a release candidate. Before release, the confirmed `/api/state` secret disclosure must be removed. For root-cause diagnosis, avoid mixing that security fix with the first controlled hardware test unless the device is reachable by untrusted LAN clients; otherwise preserve diagnostic purity and patch immediately afterward. Never expose port 80 to the public Internet.

## Verification boundary
This audit is static/source/model analysis. It does not prove ESP32 compile/link success, real heap fragmentation behavior, RF coexistence, or AsyncTCP/NimBLE timing on hardware. Those require the user's PlatformIO build and hardware run.
