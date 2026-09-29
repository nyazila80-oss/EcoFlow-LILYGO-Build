# AUDIT20.4.5.9.36.7.4 — BLE Memory Lifecycle Diagnostic

## Scope
Focused follow-up to 9.36.7.3. No CAN/RS485 protocol, PowerStream UUID/auth frame, SOC guard, JK proxy protocol, or automatic-control behavior is changed.

## Finding fixed
The prior PowerStream BLE guard used the same 18k/9k threshold both before xTaskCreatePinnedToCore() and inside the 6144-byte worker. Because the worker stack is heap-backed, that policy could admit task creation and then immediately self-block inside the worker.

## Memory policy
- Pre-task admission: free heap >= 18000, largest 8-bit block >= 9000, heap integrity OK.
- Runtime reserve after task creation and after dynamic BLE stages: free heap >= 9000, largest 8-bit block >= 6000, heap integrity OK.
- Runtime checks occur at worker entry, after PS client allocation, after connect, after GATT subscribe, and immediately before command commit.
- Existing JK/NimBLE init admission remains 20000/12000; post-client JK guard remains 8000/6000.
- Worker stack remains 6144 bytes; it is NOT reduced without hardware high-water evidence.

## Telemetry
Web/API now expose scalar checkpoints only: request, worker, aux reservation, client allocation, connect, GATT, auth, command, cleanup delta, worker stack high-water and ESP minimum free heap. No UID, key, BLE payload, or secret is exposed.

## FMEA
1. Insufficient pre-task heap -> request rejected before worker allocation.
2. Worker stack causes reserve to fall below runtime threshold -> worker fails closed before BLE reservation/connect.
3. Client allocation pressure -> checked immediately after allocation; fail closed.
4. Connect/GATT fragmentation -> checked at each stage; fail closed before auth/command.
5. Heap corruption -> heap_caps_check_integrity_all(false) blocks operation.
6. Repeated one-shots -> cleanup delta and ESP min-free make monotonic loss observable; PS client reuse remains unchanged to reduce churn.
7. Worker stack exhaustion -> existing uxTaskGetStackHighWaterMark telemetry retained; stack size is not reduced in this release.
8. Cleanup failure/disconnect timeout -> existing hard deleteClient fallback remains unchanged.

## Host simulations rerun
- ps_ble_memory_lifecycle: 2,000,000 randomized runs; 975,188 pre-task admissions; 103,968 modeled runtime fail-closed blocks; 0 unsafe-command violations.
- ps_ble_lab2: 10,000,000 checks; 0 violations.
- ps_ble_arbiter: 80,000,000 checks; 0 violations.
- resource_gate: 10,000,000 steps; 0 violations.
- ble_owner_handshake: 6,000,000 checks; 0 violations.

## Limits
No PlatformIO executable is available in the audit container, therefore ESP32 compile/link and real NimBLE allocation sizes are NOT claimed verified here. Hardware build and the first one-shot memory checkpoints are the next validation boundary.

## JK/NimBLE initialization telemetry
The JK/NimBLE owner also records pre-init, post-NimBLE, post-server, post-GATT, post-client and post-advertising free/largest-block snapshots. This makes the one-time NimBLE footprint observable separately from the PowerStream one-shot footprint.

Cleanup delta is diagnostic, not by itself a leak verdict: the first successful PowerStream run intentionally retains the dedicated disconnected NimBLE client/GATT cache for reuse. A leak suspicion requires a monotonic decline across repeated equivalent runs after that first retained allocation.
