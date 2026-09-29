# AUDIT20.4.5.9.27 RESOURCE-GATE-HARDENED

## Finding
The one-shot PowerStream BLE worker and the persistent EcoFlow cloud/TLS worker had independent admission controls. Each path was locally guarded, but they could overlap and compete for heap/largest-free-block during the most allocation-heavy phases (NimBLE GATT/client activity vs TLS/HTTP/String allocations). A pre-operation heap check alone cannot prevent a second subsystem from consuming heap immediately afterwards.

## Change
Added a process-wide atomic heavy-operation ownership gate (`resource_gate.{h,cpp}`). PowerStream BLE acquires `POWERSTREAM_BLE` before task creation and releases it on task-create failure or worker cleanup. EcoFlow cloud jobs acquire `POWERSTREAM_CLOUD` before worker/job admission and release on worker-create failure or after job completion. Thus BLE and cloud/TLS heavy operations cannot overlap, while CAN/RS485/Web/MQTT normal service remains unaffected.

Added cloud-worker diagnostics: stack high-water mark in ESP32 bytes, free heap and largest 8-bit block sampled before the cloud operation. No arbitrary new heap threshold was introduced because hardware measurements are not yet available.

## Failure semantics
Gate contention rejects/defer-fails the newly requested heavy operation; it does not silence CAN and does not alter BMS safety state. Ownership release uses compare/exchange against the expected owner so one subsystem cannot accidentally release the other's reservation.

## Verification
- resource gate adversarial model: 100 runs / 10,000,000 steps / 0 violations.
- final regression: 20 seeds / 12 static checks PASS.
- SOC/SOH: 3,000,000 ops / 0 violations (rerun earlier in this audit sequence).
- shared BLE: 18,000,000 checks / 0 violations (rerun earlier in this audit sequence).
- BLE arbiter: 80,000,000 checks / 0 violations (rerun earlier in this audit sequence).
- owner handshake: 6,000,000 checks / 0 violations (rerun earlier in this audit sequence).
- session epoch: 20,000,000 steps / 0 violations (rerun earlier in this audit sequence).
- stream fail-closed: 5,000,000 steps / 0 violations.
- backpressure model rerun separately.

## Limits
No PlatformIO executable is available in the audit environment, therefore this release is not claimed to compile. No hardware/OOM/stack measurement has been performed. Automatic SOC 20/25 PowerStream control remains OFF.
