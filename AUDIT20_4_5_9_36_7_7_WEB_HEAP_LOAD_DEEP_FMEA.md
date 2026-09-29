# AUDIT 20.4.5.9.36.7.7 — WEB/HEAP/LOAD deep FMEA

## Scope
Full source-path audit of the recurring field symptom: HTTP/WebUI is reachable after cold power-up, later becomes unreachable, and recovers after power-cycle. Reviewed Wi-Fi STA/APSTA recovery, LwIP/AsyncTCP lifecycle assumptions, AsyncWebServer routes, all three WebSockets, dashboard request cadence, NVS/Preferences in callbacks, heap fragmentation pressure, main-loop scheduling, BLE coexistence, and diagnostic observability.

## New source findings
1. The BMS dashboard does **not** create a `/bms` WebSocket. Its primary live path is REST `/api/bms`, continuously scheduled after each completed/failed request. Therefore the 9.36.7.5 WebSocket cleanup fix is valid hardening, but cannot alone explain failure of the dashboard under the current HTML.
2. `/api/bms` is a high-frequency allocation path: it builds a dynamic Arduino `String` with `reserve(4096)` and many concatenations. At the observed ~21 kB free heap this is a credible fragmentation/pressure source. It is not proven to leak.
3. `/api/state` performs Preferences/NVS reads inside an AsyncWebServer callback. This is not on the 1 s dashboard hot path, but remains a callback-latency/serialization risk and should be moved to a main-loop-owned cached snapshot in a later isolated change.
4. 9.36.7.6 correctly removes active `server.end()/begin()` rebinding. No server rebind remains in the normal loop.
5. Dashboard polling is reduced in 9.36.7.7 from 1 s to 2 s while visible and 5 s while the document is hidden. This reduces hot-path request/allocation pressure without changing BMS/CAN/RS485 timing or safety behavior.
6. `/api/bms` now records call count, in-flight concurrency, maximum concurrency, last/max synchronous JSON build time, and minimum free/largest heap observed across the handler. No request pointer is retained.
7. `ESPAsyncWebServer @ ^3.7.10` remains unpinned. Dependency drift is a reproducibility risk. It is intentionally not changed in this A/B diagnostic release; pin the exact version only after PlatformIO reports the resolved version on the user's build machine.

## FMEA
| Failure mode | Detection in 9.36.7.7 | Mitigation / behavior | Residual risk |
|---|---|---|---|
| STA disconnect | Wi-Fi event counters + reason/RSSI | bounded reconnect/full restart/APSTA recovery | AP/router RF cause remains external |
| IP lost without clean disconnect | GOT_IP/LOST_IP counters | normal STA recovery, no HTTP rebind | LwIP internal fault not directly visible |
| HTTP listener lifecycle race | suppressed-rebind counter | no end/begin churn | library-internal AsyncTCP faults remain possible |
| stale WS clients | per-endpoint counts + cleanup counter | cleanup all endpoints every 1 s | library-specific cleanup race remains possible |
| `/api/bms` request pressure | calls/inflight/max-inflight/build-us | lower browser polling cadence | dynamic String allocation remains |
| heap fragmentation | free/largest/min + handler minima | lower allocation rate; fail-closed BLE guards | no heap allocator histogram |
| request overlap after latency spike | max-inflight | sequential browser poll schedules next only after completion | other browser tabs can still overlap |
| hidden browser keeps loading ESP | request counters | hidden cadence 5 s | page remains active by design |
| NVS inside callback | source audit | unchanged in this release | open item: `/api/state` |
| main-loop starvation | loop last/max gap + heartbeat | delay(1), bounded BMS/CAN work | AsyncTCP task starvation needs hardware evidence |
| BLE/Wi-Fi coexistence pressure | BLE owner/resource + heap lifecycle | one-shot BLE, resource gate | RF coexistence requires hardware test |
| PowerStream worker heap collapse | staged BLE memory telemetry | pre/runtime heap guards | real NimBLE allocations require hardware |
| dependency drift | platformio.ini audit | identified | exact AsyncWebServer/AsyncTCP versions not yet pinned |
| whole ESP task deadlock | Serial heartbeat + loop gap | no blind reboot | no task watchdog added; intentional for diagnosis |

## Simulation / model audit
- Web load A/B model: 20,000 traces x 180 s. Old 1 s cadence = 3,600,000 requests; 9.36.7.7 cadence = 1,440,000 requests. Sum of modeled maximum concurrent requests fell from 39,558 to 29,675. Invariant violations: 0. This is a pressure model, not an ESP heap emulator.
- WEB/NETIF model: 3,000,000 states, 0 violations. Historical rebind-with-live-client states: 24,542. Stale/low-heap pressure states observed: 279,448.
- PS BLE memory lifecycle: 2,000,000 runs; admitted 1,038,357; modeled runtime aborts 70,081; unsafe command below runtime memory floor: 0.
- PS BLE Lab: 10,000,000 checks, 0 violations.
- Resource gate: 10,000,000 steps, 0 violations.
- BLE owner handshake: 6,000,000 checks, 0 violations.

## Static invariants checked
- Firmware and filesystem version must match exactly.
- No `server.end()` remains in the 9.36.7.7 source.
- `server.begin()` occurs once in setup.
- All three WS endpoints are registered and cleaned.
- Wi-Fi event callback only records atomic diagnostics; no recovery action in event task.
- PowerStream/CAN/RS485/BMS safety logic is unchanged by the 9.36.7.7 web-load change.

## Audit conclusion
9.36.7.7 is a controlled diagnostic/hardening release, not proof of root cause. The source audit weakens the hypothesis that `/bms` WebSocket leakage alone causes the current dashboard failure, because the dashboard does not open that WebSocket. The stronger remaining software hypothesis is sustained AsyncWebServer/heap pressure from REST JSON construction and/or AsyncTCP/library lifecycle under Wi-Fi events. The new counters are designed to discriminate these on hardware without power-cycling away the evidence.

Do not optimize away the dynamic JSON path, move NVS callbacks, add task watchdog resets, or pin/change AsyncWebServer in the same A/B step. Those are separate experiments if 9.36.7.7 still reproduces the failure.
