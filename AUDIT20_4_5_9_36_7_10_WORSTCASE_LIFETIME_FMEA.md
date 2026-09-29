# 9.36.7.10 — Worst-Case Lifetime / Concurrency / Heap FMEA

## Scope
Source-level audit plus synthetic host model for simultaneous lifetime pressure. This is **not** an ESP32 allocator trace and does not prove hardware behavior. Current source was inspected for task creation, heap gates, WebSocket buffers, REST String construction, NimBLE client lifetime, HeavyOp serialization, and cloud-worker lifetime.

## Verified source facts
- Persistent explicit application stacks before cloud/PS worker: 14,336 B configured.
- Lazy PowerStream cloud worker adds a persistent 6,144 B stack after first creation.
- Manual PS BLE transaction adds a temporary 6,144 B worker stack.
- HeavyOpOwner serializes PowerStream cloud and PowerStream BLE operations, so their *active heavy operation* lifetimes should not overlap. The cloud task stack itself remains allocated after its job completes.
- PS BLE admission requires >=18,000 B free heap and >=9,000 B largest 8-bit block before task creation. In-worker guard requires >=9,000 B free and >=6,000 B largest block.
- JK/NimBLE objects are persistent after initialization; PS client may be reused and is disconnected/cleaned between operations.
- WebSocket log/debug rings are fixed 4,096 B each; shared flush buffer is 1,025 B. BMS WS payload uses a fixed 160 B JSON buffer then `makeBuffer()`; allocation failure is fail-closed.
- `/api/state` reserves 2,048 B dynamic String and reads Preferences in callback; `/api/bms` and `/api/bms/full` reserve 4,096 B dynamic Strings with many temporary String conversions.
- BMS WS pushes every 250 ms; log/debug flush every 50 ms; all WS endpoints cleanup every 1 s and ping every 15 s.
- Current `/api/state` exposes stored Wi-Fi and MQTT passwords while Basic Auth is disabled: confirmed security defect, independent of the stability root cause.

## Lifetime collision matrix
| State | Persistent app stacks | Added transient | Main risk |
|---|---:|---|---|
| A: JK/NimBLE + Web | 14,336 B + framework tasks | REST/WS buffers | REST String/AsyncTCP fragmentation |
| A after cloud was ever used | 20,480 B + framework tasks | REST/WS buffers | reduced permanent margin even while cloud idle |
| C: PS auth-only | 14,336 or 20,480 B + framework tasks | 6,144 B PS worker + NimBLE client/GATT/auth + REST/WS | largest-block collapse / fail-closed runtime guard |
| D: PS command | same as C | command/verify buffers and notify traffic | same plus command/ACK timing |

Cloud active job and PS BLE transaction are intentionally serialized; therefore a model that sums both *active* workers as independent heavy operations would be wrong. The persistent cloud task stack, however, can coexist with a later PS BLE worker.

## FMEA
| Failure mode | Cause | Effect | Detection/control | Residual priority |
|---|---|---|---|---|
| Largest contiguous block collapses | REST String churn + AsyncTCP + NimBLE/GATT | Web request/WS/BLE allocation fails while total heap still looks adequate | largest8/min heap, PS pre/runtime guards, WS fail-closed | HIGH |
| Permanent margin drops after cloud first use | cloud task never deleted | later Web/BLE operations start with less headroom | cloud stack HWM/heap-before | MED-HIGH |
| PS worker passes admission then falls below runtime reserve | 6,144 B task stack + GATT/client allocations + concurrent web traffic | auth/command aborts | runtime heap/largest guard | MED-HIGH; expected fail-closed outcome |
| WebUI becomes unreachable while heartbeat/Wi-Fi remain alive | AsyncTCP/request allocation starvation or client lifecycle | UI failure, firmware still running | heartbeat, Wi-Fi event counters, WS counts, HTTP diag | HIGH hypothesis, hardware proof needed |
| WS allocation pressure | makeBuffer cannot allocate contiguous block | telemetry/log message dropped | fail-closed drop; cleanup | LOW-MED safety, useful diagnostic |
| NVS work inside async callback | flash/NVS latency + allocation | request latency/stall contribution | callback audit | MEDIUM |
| Credentials readable from `/api/state` | Basic Auth removed but secrets serialized | local credential disclosure | source audit | HIGH security; confirmed |
| JK app and PS BLE contend for shared BLE | concurrent ownership | connection instability | JK app admission block + AUX reservation/recheck | LOW-MED after guards |
| Cloud and PS active operation overlap | missing serialization | heap/timing collision | HeavyOpOwner | LOW in audited app logic |

## Synthetic worst-case model
`host_sim_worstcase_lifetime_93710.py` runs 2,000,000 randomized lifetime states. It models REST/WS transient pressure, current 18k/9k PS admission, 9k/6k runtime guard, 6,144 B worker allocation, extra GATT/client pressure, and HeavyOp serialization.

Result from this audit run:
- 2,000,000 states
- 0 modeled invariant violations
- 191,078 PS requests admitted
- 169,541 admitted requests reached the modeled runtime low-memory fail-closed region
- 27,245 modeled heavy-operation overlaps were blocked by serialization
- 21,676 synthetic web-pressure allocation events

The high runtime-abort count is **not a predicted hardware failure rate**. The random distribution intentionally stresses values close to the thresholds. Its significance is structural: a transaction can legitimately pass the pre-task 18k/9k gate and then cross the 9k/6k runtime gate after worker/GATT allocations. Current code is designed to abort rather than continue unsafely.

## Audit conclusion
The current strongest stability hypothesis remains **contiguous-heap/resource-margin pressure**, not a proven leak and not a proven JK-BLE defect. The most informative hardware discriminator is the trajectory of `largest8` across A -> C -> cleanup, especially after the cloud worker has previously been created.

### Release/test gates
1. Do not restore Web Basic Auth for the stability test; keep OTA protection.
2. Before a production release, stop serializing stored Wi-Fi/MQTT passwords in `/api/state`.
3. Build/compile is still an external gate because PlatformIO is unavailable in this audit environment.
4. Hardware A/C/D run should record free heap, largest8, min heap, PS memory snapshots, WS client counts, Wi-Fi event counters, HTTP `/api/bms` build metrics and task HWM.
5. If A fails without any PS transaction, optimize/instrument Web/AsyncTCP first. If only C fails, focus shared NimBLE/GATT/resource margin. If C succeeds and D fails, focus command/ACK/verify delta.
