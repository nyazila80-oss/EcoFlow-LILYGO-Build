# AUDIT20.4.5.9.36.7.4 — BLE MEMORY LIFECYCLE DIAG

## Scope
9.36.7.4 instruments the real JK/NimBLE and PowerStream BLE memory lifecycle and separates pre-task admission from in-worker runtime reserve. No CAN/RS485 protocol, EcoFlow GATT UUID, auth payload, priority command, SOC guard, or automatic reconnect/control semantics are changed.

## Memory policy
- JK/NimBLE pre-init admission remains 20,000 B free / 12,000 B largest 8-bit block.
- PowerStream pre-task admission: 18,000 B free / 9,000 B largest block.
- PowerStream worker runtime reserve: 9,000 B free / 6,000 B largest block, checked at worker entry, after client allocation, after connect, after GATT, and before command.
- Worker stack remains 6,144 B. Admission and runtime thresholds are intentionally separate because task creation consumes heap before worker entry.
- Heap integrity remains mandatory.

## Diagnostics
JK checkpoints: pre-init, post NimBLE init, post server, post GATT, post JK client, post advertising, ESP minimum free heap.
PowerStream checkpoints: admission/request, worker entry, aux reservation, PS client, connect, GATT, auth, command, transaction minima, worker stack high-water, cleanup delta.
All diagnostics are scalar memory values; no UID, key, password, packet payload, or other secret is exposed.

## FMEA
1. Low/fragmented heap before NimBLE: init deferred; no partial init.
2. Partial NimBLE allocation failure: existing SAFE HOLD remains.
3. PS admission below 18k/9k: request rejected before task creation.
4. Worker allocation failure: request fails closed and resource gate is released.
5. Task creation consumes more than expected: worker-entry 9k/6k guard aborts before BLE ownership/connect.
6. PS client/connect/GATT memory pressure: stage runtime guards abort before command.
7. Heap integrity failure: admission/runtime guard rejects.
8. Cleanup: client is disconnected/reused; before/after heap and largest-block delta are recorded to identify drift/leak across repeated one-shots.
9. Stack pressure: uxTaskGetStackHighWaterMark is recorded in bytes on ESP32.
10. Diagnostics themselves use fixed scalar atomics/snapshots; no callback-time dynamic allocation was added.

## Simulation / regression
- host_sim_ps_ble_lab2.py: 10,000,000 checks, 0 violations.
- host_sim_ps_ble_arbiter.py: 80,000,000 checks, 0 violations.
- host_sim_resource_gate.py: 10,000,000 steps, 0 violations.
- host_sim_ps_ble_memory_lifecycle_93674.py: 2,000,000 randomized memory states, 0 unsafe admitted states crossing modeled stage guards. Runtime aborts are expected fail-closed outcomes.

## Hardware boundary
Host simulation cannot establish actual NimBLE-Arduino allocation sizes on this ESP32. Hardware measurements from 9.36.7.4 are therefore the acceptance evidence. First test should inspect MEM values before Storage. Then one Storage one-shot may be used to populate client/connect/GATT/auth/cleanup checkpoints. Repeated one-shots should not show monotonic cleanup loss.

## Acceptance guidance
- PRECHECK must be all OK/FREI before command.
- Runtime free/largest must stay >= 9,000/6,000 B at guarded stages.
- worker_stack_min_bytes should retain a meaningful margin; treat <1,024 B as a stop condition for further testing.
- Repeated cleanup delta should stabilize; persistent negative drift across repeated one-shots requires leak investigation.
