# AUDIT 20.4.5.9.36.7.10 — Full Project Audit

## Scope
Full static audit of the current project tree: 315 files, ~1.8 MiB, 9,223 lines across src/include/data/platform files. Reviewed boot/lifecycle, BMS/RS485, CAN/TWAI, EcoFlow emulation, JK BLE proxy, PowerStream BLE, cloud API, Wi-Fi/LwIP/AsyncWebServer, WebUI/REST/WS, OTA/SPIFFS, NVS/config, tasks/mutexes/atomics, heap/stack behavior, partitions and existing host simulations.

## Verification boundary
This is source/model verification, not hardware proof. PlatformIO is not installed in the audit environment, so no ESP32 compile/link/flash test is claimed.

## High-level result
The safety-critical architecture is substantially hardened: bounded BMS parsing, CAN task separation, serialized TX, fail-closed resource ownership, BLE epoch/queue guards, loop-stall CAN gate, TWAI bus-off recovery, and staged PowerStream BLE paths are present. No static evidence of a single obvious deterministic crash/root cause was found.

The dominant residual risk remains memory/network pressure around the WebUI and concurrent radio/network workloads. The current code still constructs large JSON responses with Arduino String in AsyncWebServer callbacks (notably /api/state, /api/bms, /api/bms/full and PowerStream status). This is a credible fragmentation/transient-allocation mechanism on a device previously observed near ~21 KiB free heap. It is not proven causal.

## Key findings

### F1 — Large dynamic JSON in AsyncWebServer callbacks — HIGH diagnostic priority
Multiple handlers reserve/build 2–4 KiB+ Arduino Strings and concatenate many temporary Strings. /api/bms and /api/bms/full are especially allocation-heavy. With AsyncTCP callbacks and BLE/Wi-Fi sharing limited internal RAM, this can reduce largest contiguous 8-bit block even when total free heap appears adequate.
Mitigation already present: reduced dashboard polling and per-/api/bms heap/build diagnostics.
Recommended next hardening after hardware evidence: fixed/bounded response streaming or preallocated snapshot serialization; avoid many temporary String concatenations.

### F2 — /api/state includes configuration/NVS-derived work in request context — MEDIUM/HIGH
Preferences and configuration access in web request paths increases callback latency and cross-subsystem contention. Snapshotting config in the main/config owner and serving an immutable snapshot would reduce this surface.

### F3 — Dependency reproducibility — MEDIUM
ESPAsyncWebServer uses ^3.7.10 and espressif32 platform is unpinned. A future clean build may resolve different dependency versions. This is not a runtime root cause for an already-built binary, but it weakens reproducibility and regression bisecting. Pin exact known-good versions only in a separate controlled change.

### F4 — Task/stack budget is non-trivial — MEDIUM
Explicit application tasks include CAN log 2560, CAN alert 2560, CAN RX 3072, CAN decode 4096, diag 2048, PowerStream cloud 6144, and transient PowerStream BLE worker stack. NimBLE/AsyncTCP/Wi-Fi system tasks add additional internal RAM usage. Existing high-water diagnostics are valuable; hardware measurements are required before resizing.

### F5 — Cloud worker lifetime — MEDIUM
The cloud worker is a persistent 6144-byte task once created. It is protected by a heavy-operation owner and diagnostics, but its persistent stack reservation can materially alter later BLE/Web heap headroom. A/B hardware testing should include before/after first cloud operation if cloud API is used.

### F6 — WebSocket lifecycle — LOW/MEDIUM after fixes
All three WS paths now receive cleanup and bounded ring buffers are used for logs. Historical missing /bms cleanup was real, but the current BMS dashboard primarily uses REST, so it is unlikely to be the sole current GUI failure mechanism.

### F7 — Web Basic Auth — LOW as current root cause; MEDIUM historical amplifier
Normal WebUI Basic Auth has been removed while OTA remains protected. Historical 401/retry and WS reconnect behavior can amplify request load but cannot be the necessary cause of a failure that persists on NO-AUTH builds.

### F8 — Wi-Fi listener rebind — reduced risk after 9.36.7.6
Active server.end()/begin() on STA/IP recovery is no longer performed. Wi-Fi event counters now permit classification of association/IP loss versus HTTP/AsyncTCP failure.

### F9 — BLE coexistence/resource ownership — controlled but hardware-dependent
JK proxy and PowerStream client share NimBLE. Owner handshake/resource gate/session epoch/backpressure guards model cleanly. RF coexistence, NimBLE allocator behavior and real GATT timing cannot be proven by host simulation.

### F10 — Historical regression evidence is incomplete — MEDIUM diagnostic limitation
The tree contains extensive audit history but not a complete byte-identical pre-20.4.5.8 source/commit baseline. Therefore claims about the exact first regression must remain conditional until an actual historical tree/build is available.

### F11 — Old host simulations contain stale release assertions — PROCESS finding
host_sim_final_regression.py and host_sim_v24_final_audit.py fail current-tree static assertions because they encode historical version/string/setter expectations. Their modeled state logic is not automatically invalid, but they cannot be counted as current-release PASS evidence without updating the test oracle. This is an important audit hygiene issue.

### F12 — Partition/OTA layout — PASS static
Custom 4 MiB layout provides dual 0x1C0000 OTA app slots, 0x60000 SPIFFS, NVS/otadata/coredump. First migration still requires USB because OTA cannot replace the partition table.

## FMEA summary
Highest RPN families for the observed GUI symptom:
1. Dynamic String/JSON allocation + AsyncTCP concurrency + low largest block.
2. Wi-Fi/AsyncTCP callback/network starvation while main loop remains alive.
3. BLE/NimBLE or cloud task activation reducing heap headroom and exposing F1/F2 rather than being the primary defect.
4. NVS/config work in async request context.
5. Dependency/version drift during rebuild (reproducibility, not direct field failure).

Lower current probability as sole root cause: removed Web Basic Auth, old server rebind, missing /bms WS cleanup.

## Simulation rerun on current tree
PASS:
- staged JK/PowerStream coexistence: 3,000,000 states / 0 violations
- web-auth model: 4 x 250,000 events / 0 invariant violations
- web heap/load model: 20,000 runs / 0 violations
- web/Wi-Fi lifecycle: 3,000,000 states / 0 violations
- BLE owner handshake: 6,000,000 checks / 0
- resource gate: 10,000,000 steps / 0
- PS BLE memory lifecycle: 2,000,000 runs / 0; runtime aborts are intentional fail-closed outcomes
- CAN bus-off recovery: 10,000,000 checks / 0
- loop-stall CAN gate: 10,000,000 checks / 0
- config single-owner: 2,000,000 steps / 0

NOT COUNTED AS PASS:
- host_sim_final_regression.py: current-tree static oracle rejects FW version (historical expectation).
- host_sim_v24_final_audit.py: historical static checks reject current version/setter shape. Modeled 2,000,000 operations had 0 violations, but script overall correctly returns FAIL due stale oracle.

## Audit conclusion / release gate
Do not label 9.36.7.10 fully hardware-validated. It is suitable as a diagnostic candidate after Clean+Build succeeds. Before further functional changes, obtain hardware evidence in staged operation and capture /api/net/health + /api/bms diagnostics + serial heartbeat at the moment of GUI failure.

Recommended engineering order after hardware capture:
1. If Wi-Fi remains associated and heartbeat continues: refactor heavy REST JSON generation first.
2. If LOST_IP/DISCONNECTED rises: investigate Wi-Fi/LwIP/RF coexistence and disconnect reason.
3. If heartbeat stops/min heap collapses: inspect task/heap starvation, cloud/BLE activation and stack HWM.
4. Only after this evidence, make one controlled change per A/B build.
