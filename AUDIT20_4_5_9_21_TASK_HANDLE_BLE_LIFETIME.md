# AUDIT20.4.5.9.21 — Task-handle / BLE lifetime hardening

## Findings fixed
1. CAN diagnostic stack-watermark readers could race a failed late CAN task-start rollback: task handles are assigned by xTaskCreate before the all-or-nothing core pipeline decision, while diagAlive can query the handles concurrently. Both watermark getters now take the existing recursive CAN-init lock before reading/dereferencing a TaskHandle_t.
2. JK BLE `sInitialized` was a plain bool published by the Arduino loop but read by the PowerStream BLE worker/API. It is now an acquire/release atomic.
3. JK BLE `sRestartAdvertisingPending` was a plain bool written from auxiliary-slot release and deferred BLE transition paths and consumed by jkBleProxyTick. It is now an acquire/release atomic, retaining the rule that actual advertising restart occurs in jkBleProxyTick.

## Deliberately not changed
- Automatic 20/25 SOC control remains disabled.
- BMS stale CAN fail-closed behavior is unchanged.
- PowerStream physical enforcement is still not claimed without hardware validation.
- No successful PlatformIO compile is claimed in this environment.

## Regression
- host_sim_final_regression: 20 seeds, 12 static checks PASS.
- SOC/SOH hardened: 3,000,000 ops, 0 violations; deterministic hysteresis/disable reset/SOH no-fake-enforcement PASS.
- PS BLE arbiter: 100,000 runs / 80,000,000 checks / 0 violations.
- PS BLE lab2: 20,000 runs / 10,000,000 checks / 0 violations.

## Remaining audit targets
NimBLE cross-task API ownership (notably auxiliary reservation advertising stop), event FIFO overflow recovery, queue/task lifetime under forced allocation failure, recorder/sequencer state, WebSocket disconnect stress, and hardware stack/heap minima.
