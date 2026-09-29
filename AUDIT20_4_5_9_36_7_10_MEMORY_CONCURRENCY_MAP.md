# AUDIT20.4.5.9.36.7.10 — Memory / Concurrency / Lifetime Map

## Scope
Static source audit of the current 9.36.7.10 tree. This is a source-level map, not a hardware heap trace or compile/link proof.

## 1. Explicit application tasks
| Task | Stack argument | Core | Priority | Lifetime / trigger | Notes |
|---|---:|---:|---:|---|---|
| canLog | 2560 | 1 | 3 | boot / persistent | CAN log path |
| canAlert | 2560 | 0 | 9 | boot / persistent | TWAI alert path |
| canRx | 3072 | 0 | 8 | boot / persistent | CAN receive |
| canDecode | 4096 | 0 | 7 | boot / persistent | CAN decode |
| diagAlive | 2048 | 1 | 1 | boot / persistent | heartbeat / HWM diagnostics |
| psCloud | 6144 | 1 | 1 | lazily created, then persistent | cloud worker sleeps when idle; its task stack remains allocated |
| psBleOneShot / psBleAuthProbe | 6144 | 1 | 1 | temporary per admitted BLE transaction | deleted in common epilogue |

Explicit application task-stack arguments total 14,336 bytes before cloud/BLE workers; 20,480 with persistent cloud worker; 26,624 with cloud + active PS BLE worker. These figures are configuration arguments and do not include TCBs, system tasks, NimBLE, Wi-Fi/LwIP, AsyncTCP, allocator overhead, or library buffers.

## 2. Large fixed/static buffers visible in project
- WebSocket CAN ring: 4096 B.
- WebSocket DEBUG ring: 4096 B.
- Shared WebSocket flush buffer: 1025 B.
- JK BMS frame buffer: 340 B.
- JK BMS raw RX buffer: 384 B.
- MQTT JSON stack buffer: 512 B.
- PS BLE decrypt/plain local arrays: up to 512/517 B in notification processing; encrypt scratch 128 B.
- Several 256–384 B local JSON/log buffers.

The two WebSocket rings + flush buffer alone reserve 9217 B of static storage. This is bounded and is not, by itself, a leak.

## 3. High-risk dynamic-allocation paths
### /api/state
- Performs Preferences/NVS reads inside AsyncWebServer callback.
- Builds a dynamic Arduino `String`, reserve(2048), followed by many temporary String concatenations.
- Current code also returns stored Wi-Fi and MQTT passwords. This is a confirmed credential-disclosure defect while Web Basic Auth is disabled and should be fixed before release.

### /api/bms
- reserve(4096) plus many numeric-to-String temporaries and arrays of cells/wire values.
- High-frequency endpoint; therefore the most important fragmentation/load candidate.
- Existing diagnostics already track calls, inflight, build time, min free heap and min largest block.

### /api/bms/full
- reserve(4096), large diagnostic payload and many temporary Strings.
- Lower expected frequency than `/api/bms`, but high transient allocation footprint.

### PowerStream status/config endpoints
- Multiple chained dynamic String constructions. Smaller frequency but can overlap with BLE worker allocation.

### AsyncWebSocket transmission
- `makeBuffer()` dynamically allocates a WebSocket message buffer. Code has fail-closed handling, but allocation pressure is real.

## 4. Concurrency ownership map
- CAN TX: static mutex serializes transmission.
- BMS object: static mutex protects object snapshots/access.
- MQTT config NVS: static mutex.
- Web pending core/toggle/guard changes: atomics + portMUX; applied by main-loop owner.
- PowerStream cloud and BLE: HeavyOpOwner/resource gate prevents intended heavy-operation overlap.
- JK/PS BLE: AUX connection reservation and JK-app-connected checks gate PS transactions.
- WebSocket CAN/DEBUG rings: independent static mutexes.
- Many cross-context counters/state values are atomic.

No obvious unbounded queue was identified in these audited application paths. The principal remaining concurrency risk is library/system resource contention (AsyncTCP/Wi-Fi/NimBLE) under low contiguous heap rather than a plainly unprotected application object.

## 5. Core/lifetime collision map
Core 0 carries high-priority CAN alert/RX/decode tasks. Core 1 carries Arduino/main-loop context plus CAN logging, diagnostics, lazy cloud worker and temporary PS BLE worker. Wi-Fi/LwIP/AsyncTCP/NimBLE add framework tasks/resources outside this explicit application map.

Worst explicit application-stack coexistence occurs after cloud worker has been created and while a PS BLE transaction is active: 26,624 bytes of configured application task stacks, before system/library tasks and dynamic allocations.

## 6. Fragmentation hypothesis
The dangerous state is not simply `free heap == low`. A request can fail while total free heap remains apparently adequate if `largest_free_block` has fallen below the contiguous allocation required by String growth, AsyncTCP/WebSocket buffers, NimBLE client/GATT objects, or task creation.

Therefore the diagnostic tuple must be treated as:
`free_heap + largest_8bit_block + min_heap + task HWM + active HTTP/WS/BLE/cloud state`.

## 7. NVS / callback audit
Confirmed direct Preferences reads remain in `/api/state`; network/MQTT-related callbacks also perform configuration work. Main-loop ownership has already been introduced for several write paths, which is good. The architectural target should be immutable/fixed-size snapshots for web reads and queued owner writes, keeping flash/NVS work out of AsyncWebServer callbacks.

## 8. FMEA additions
| Failure mode | Effect | Cause candidate | Existing control | Residual risk |
|---|---|---|---|---|
| Largest block collapse | WebUI stalls/alloc fails while board still runs | repeated String/AsyncTCP/BLE allocations | heap/largest diagnostics, WS fail-closed | HIGH |
| Cloud worker persistent footprint | later BLE/web operations have less headroom | lazy worker never deleted | heavy-op serialization | MED-HIGH |
| PS BLE temporary stack/client/GATT pressure | WebUI failure around phase C/D | simultaneous library allocations | admission/runtime heap guards, cleanup | MED-HIGH |
| `/api/bms` allocation churn | progressive fragmentation/load | 4K String + many temporaries at high frequency | timing/min-heap diagnostics | HIGH |
| NVS in async callback | latency/contention | Preferences reads in web callback | limited frequency | MEDIUM |
| Credential disclosure via `/api/state` | local-network credential exposure | auth removed but secrets still serialized | none sufficient | HIGH security; confirmed |
| WS client accumulation | retained TCP/WS resources | stale clients/reconnect | centralized cleanup all sockets | reduced to LOW-MED |
| task stack exhaustion | crash/corruption | insufficient stack | HWM on selected workers/tasks | MEDIUM; hardware measurement needed |

## 9. Audit conclusion
No source-level evidence establishes one single root cause. The strongest combined hypothesis is a resource-margin/fragmentation problem in which high-frequency dynamic web serialization and AsyncTCP coexist with NimBLE and optional workers. BLE may be the trigger that consumes the remaining contiguous memory rather than the primary defect.

Before release, the `/api/state` credential disclosure should be corrected independently of the stability experiment. For root-cause isolation, do not simultaneously rewrite all web serialization before collecting the staged A/B/C hardware evidence; doing so would destroy the diagnostic baseline.

## 10. Recommended instrumentation gate
On hardware capture, at minimum, before/after A, C and D:
- free heap
- largest 8-bit free block
- minimum free heap
- CAN RX/decode task HWM
- diag HWM
- PS BLE worker HWM
- cloud worker HWM if it has ever been created
- WebSocket client counts
- `/api/bms` call/inflight/max-build/min-heap/min-largest counters
- Wi-Fi disconnect/GOT_IP/LOST_IP counters
- active HeavyOp owner / JK AUX state / PS BLE stage

