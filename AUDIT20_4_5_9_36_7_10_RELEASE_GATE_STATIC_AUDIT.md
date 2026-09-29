# 9.36.7.10 — Static Release-Gate Audit (Phase 4)

Scope: actual `/mnt/data/work9380` source tree. Static review focused on deadlock/lock ordering, cross-core state, task lifetime, NimBLE client/callback lifetime, bounded buffers, NVS paths, fail-closed behavior, and validity of current host simulations.

## Executive result

**Gate status: HOLD for production release; suitable for controlled diagnostic hardware build after successful local PlatformIO compile/link.**

No single deterministic deadlock, obvious fixed-buffer overflow, or HeavyOp overlap was found in the reviewed application paths. However, there are release-blocking/security and diagnostic-quality items that should not be conflated with the WebUI root-cause experiment.

### Confirmed release blocker: credentials exposed by `/api/state`
`src/web.cpp` reads `net/pass` and `mqtt/pass` from Preferences inside `/api/state`. With Web Basic Auth intentionally disabled, returning these values to the browser makes them retrievable by any client that can reach that endpoint. This is a production-release blocker. For the diagnostic A/B build, do not restore Basic Auth merely to hide this; instead make secrets write-only in the later production hardening patch.

### Memory / WebUI root-cause risk remains HIGH
The status/API paths construct large dynamic `String` JSON responses while AsyncTCP/NimBLE/Wi-Fi coexist. Free heap alone is insufficient; largest contiguous 8-bit block is the critical metric. `/api/bms`, `/api/bms/full`, `/api/state`, PowerStream BLE status, and cloud-job status remain fragmentation/allocation-pressure candidates.

### Cloud worker lifetime is bounded logically but persistent in RAM
`psCloud` is created once with stack size 6144 and loops forever. HeavyOp ownership serializes cloud work vs PowerStream BLE work, but the idle cloud task stack remains allocated and can reduce later BLE/Web allocation margin.

## Concurrency / deadlock audit

### HeavyOp gate
`resource_gate.cpp` uses one atomic owner CAS. Release requires the expected owner and mismatches are counted; no lease stealing exists. This prevents application-level PowerStream Cloud and PowerStream BLE heavy operations from executing concurrently.

### Mutex/critical-section ordering
Reviewed locks include PowerStream API recursive mutex, cloud job mutex, BMS object mutex, CAN TX mutex, CAN init mutex, Wi-Fi/MQTT NVS mutexes, WebSocket ring mutexes, and several short `portMUX` sections. No confirmed circular lock ordering was found in the reviewed call graph. Critical sections are bounded copies/scalar updates; no network/NVS/GATT operation was found while holding those portMUX critical sections.

### Potential starvation / latency rather than deadlock
Several paths use bounded waits (50–250 ms) or fail immediately; BMS object lock uses `portMAX_DELAY`. This is not a proven deadlock, but future code must not call into BMS object operations while holding a lock that BMS-side code can acquire in reverse order. No such reverse chain was confirmed in this tree.

## Task lifetime audit

- CAN tasks are created during init and explicitly deleted on partial-init failure.
- Diagnostic heartbeat task is persistent by design.
- Cloud worker is persistent after first creation by design.
- PowerStream BLE one-shot worker self-deletes on the common epilogue.
- PowerStream BLE task-creation failure paths reset transaction depth/release HeavyOp in the current 9.36.7.10 implementation.

No confirmed orphaned HeavyOp owner was found in the reviewed PowerStream BLE common worker exit path.

## NimBLE client / callback lifetime

PowerStream BLE keeps a reusable `NimBLEClient*`. `cleanupClient()` requests disconnect, waits up to 1200 ms, and deletes the client only if it remains connected. Remote characteristic pointers are cleared in cleanup. Notify callbacks copy bounded data into a fixed queue; parsing occurs in the worker, not in the host callback.

Risk classification: **MEDIUM diagnostic risk, not a confirmed use-after-free.** A hardware-only race can still exist between late host callbacks and client teardown. Existing queue/epoch handling and bounded callback work reduce the risk. The current notify-race host model passed 10,000,000 modeled events with zero modeled invalid notifications, but this does not prove NimBLE host internals.

## Buffer / bounds audit

Positive controls found:
- WebSocket log rings reject lines larger than ring capacity, preventing an infinite drop loop.
- `snprintf` is used for fixed diagnostic buffers in reviewed hot paths.
- PowerStream notify callback uses a fixed maximum packet size and bounded queue.
- PowerStream crypto padding checks the local 128-byte buffer before encryption.
- CAN reassembly has explicit oversize/length/CRC drop paths.

No obvious deterministic fixed-array overflow was confirmed in the inspected application code. This is a static conclusion, not compiler/sanitizer proof.

## NVS / Preferences audit

NVS work still occurs in some AsyncWebServer callbacks, notably `/api/state` reads. Wi-Fi and MQTT mutation paths use deferred/serialized helpers in newer code. Production architecture should move all secrets/config reads to owned snapshots and all writes to the main/config owner, leaving Async callbacks to consume snapshots/queue mutations only.

## Fail-closed audit

Positive controls:
- PS BLE admission requires fresh BMS data, JK app free, Wi-Fi stability, heap/largest-block reserve, cooldown, and HeavyOp availability.
- A second runtime heap guard exists after worker/client/connect stages.
- WebSocket allocation failure drops non-critical logging rather than retrying allocation.
- CAN malformed/oversize/CRC-invalid reassembly is dropped.
- HeavyOp does not steal stale owners.

Diagnostic semantic issue: `sTxFail` is also incremented for AUTH_ONLY failure, so it is an operation-failure counter rather than strictly a command-transmit failure counter. `auth_only_fail` disambiguates it, but naming should be cleaned later.

## Source/version hygiene findings

The current tree contains historical audit comments such as `AUDIT20.4.5.9.11` in `powerstream_ble_lab.cpp` and `AUDIT20.4.5.9.13` in `powerstream_api.cpp` while the packaged release is called 9.36.7.10. These comments do not by themselves alter runtime behavior, but they are provenance/version-hygiene debt and make audit traceability harder. Before a production release, source comments and release manifest should be normalized.

## Simulation re-run

Re-run on this tree:

- staged JK/PS coexistence: 3,000,000 states, 0 violations
- BLE owner handshake: 6,000,000 checks, 0 violations
- resource gate: 10,000,000 steps, 0 violations
- Web/Wi-Fi lifecycle: 3,000,000 states, 0 violations
- CAN bus-off recovery: 10,000,000 checks, 0 violations
- worst-case lifetime: 2,000,000 runs, 0 invariant violations; 159,866 PS admissions; 11,742 runtime fail-closed outcomes; 28,883 HeavyOp overlaps blocked
- notify race model: 10,000,000 events, 0 modeled invalid notifications
- cloud job FSM: 1,000,000 runs / 4,000,000 checks, 0 violations
- resource-gate lifetime: 10,000,000 checks, 0 violations (intentional release-mismatch injections are part of the model)
- web heap-load model: 20,000 runs, 0 model violations
- config single-owner: 2,000,000 steps / 1,333,021 checks, 0 violations

### Important simulation coverage weakness
The current `host_sim_worstcase_lifetime_93710.py` reported `web_pressure_events: 0` and `ws_failclosed_drops: 0`. Therefore that model did **not** meaningfully exercise the WebUI allocation-pressure corner we care about most. Its zero violations must not be used as evidence that Web/heap pressure is safe. The separate `host_sim_web_heap_load_9377.py` is useful as a load/concurrency model, but it also cannot reproduce real ESP32 heap fragmentation/AsyncTCP allocator behavior.

This is the most important audit correction in Phase 4: prior simulation counts are valid for their modeled invariants, but coverage of the suspected real WebUI failure mechanism remains incomplete.

## Release-gate matrix

| Area | Status | Meaning |
|---|---|---|
| HeavyOp serialization | PASS (model/static) | no app-level Cloud/PS-BLE overlap found |
| Fixed-buffer bounds | PASS with limits | no obvious deterministic overflow found |
| Task cleanup | PASS with persistent-task caveat | PS BLE self-cleans; Cloud remains resident by design |
| NimBLE teardown/callback race | CONDITIONAL | hardened/modelled, hardware timing still required |
| Web heap fragmentation | OPEN / HIGH | strongest unresolved WebUI candidate |
| AsyncTCP/Wi-Fi runtime | OPEN | hardware evidence required |
| NVS in Async callbacks | TECH DEBT / MEDIUM | should be snapshot/queue architecture |
| `/api/state` secrets | FAIL for production | passwords must be write-only |
| Source provenance/version hygiene | WARN | historical audit tags inconsistent |
| PlatformIO compile/link | NOT VERIFIED HERE | must pass on user's build environment |

## Next gate

Do not claim production-ready. The next meaningful gate is a clean PlatformIO build, firmware + filesystem upload, then controlled hardware A1/A2/C1/C2/D testing while recording free heap, largest block, min heap, task HWM, WS client counts, HTTP build latency/inflight, Wi-Fi events, BLE stage, and HeavyOp owner. If WebUI fails, do not reboot until serial/router/API evidence is captured.
