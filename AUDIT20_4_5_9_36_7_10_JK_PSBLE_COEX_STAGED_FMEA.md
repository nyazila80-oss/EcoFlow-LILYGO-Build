# AUDIT 20.4.5.9.36.7.10 — JK / PowerStream BLE staged coexistence

## Objective
Isolate the WebUI regression without treating JK-BLE as the default culprit. JK-BLE remains part of the baseline because it was reported stable with the app/WebUI in earlier builds.

## Test matrix
- A: JK-BLE + JK app + RS485 + CAN + Wi-Fi/WebUI. No PowerStream BLE transaction.
- B: same runtime with PowerStream BLE configured/enabled but IDLE. No worker/connect/auth/command.
- C: one-shot PowerStream connect -> service/characteristics -> notify subscribe -> auth, then cleanup/disconnect. Explicitly no supply/storage frame.
- D: existing full one-shot path including priority command and fresh-ACK verification.

C/D retain the existing shared-BLE safety rule: a connected JK app blocks the PowerStream one-shot. This release does not weaken that invariant merely to make a test easier.

## FMEA highlights
1. C accidentally writes priority command — guarded by PsTxnDepth::AUTH_ONLY branch immediately after successful auth and before memCommand/SENDING/supplyFrame/writeValue. Severity high; detection via command epoch/tx counters and source audit.
2. Stale 9.36.7.9 legacy NVS flag suppresses PS runtime — runtime suppression removed in main loop and WS-BMS push; regressionLegacyApplied() is compatibility-only and always false.
3. Auth-probe overlaps full command/config write — existing sConfigGate + sWorkerRunning + HeavyOpOwner serialization retained.
4. JK app connection races PS admission — existing jkBleProxyAppConnected() rejection plus reserveAuxConnection/auxSlotReady recheck retained.
5. Heap collapse on worker creation/connect — existing pre-task and runtime heap/largest-block integrity gates retained.
6. Auth probe leaves PS connected — common cleanupClient() path runs for success and failure before aux slot release.
7. Auth-only mode leaks into next full operation — sTxnDepth reset to FULL in common worker epilogue and on task-create failure.
8. C changes CAN/RS485 safety behavior — no CAN/BMS/low-SOC code changed; fresh BMS telemetry remains an admission prerequisite.
9. WebUI diagnosis confounded by automatic reconnect — PS BLE remains manual one-shot; no scan/periodic reconnect added.
10. Persisted .9 legacy switch confuses UI — legacy-like control removed from dashboard; .10 staged panel is non-persistent and operation-driven.

## Static audit assertions
- main loop always calls powerStreamBleLabTick().
- /bms WS push no longer depends on legacy A/B state.
- auth-probe has same-origin guard and normal remote-auth wrapper.
- AUTH_ONLY exits before supplyFrame()/priority write.
- full Storage/Supply endpoint remains unchanged except obsolete legacy blocking removed.
- JK BLE isolation switch from .8 is retained only as an optional secondary control, not the primary regression method.

## Simulation
`host_sim_coex_staged_93710.py`: 3,000,000 randomized phase/admission states, 0 invariant violations.

## Validation boundary
This is source/static + host-model validation. It is not an ESP32 compile/link result and cannot prove RF coexistence, NimBLE/AsyncTCP scheduling, or hardware stability. Hardware A/B/C/D evidence is required.

## Regression simulations re-run
- BLE owner handshake: 6,000,000 checks / 0 violations.
- Resource gate: 10,000,000 steps / 0 violations.
- PS BLE memory lifecycle: 2,000,000 runs / 0 violations (runtime aborts are modeled fail-closed outcomes, not invariant failures).
- PS BLE arbiter: 80,000,000 checks / 0 violations.
- PS BLE lab: 10,000,000 checks / 0 violations.
- WEB/NETIF lifecycle: 3,000,000 states / 0 violations.

## Interpretation caution
Phase B does not claim a second PowerStream NimBLE stack exists. JK already initializes the shared NimBLE host. In the present architecture, an enabled/configured but idle PowerStream path creates no PS worker and no PS connection. Therefore A->B is primarily a configuration/idle control, while the first meaningful additional runtime BLE load occurs at C (worker + auxiliary slot + PS client/connect/GATT/auth). This distinction is intentional and must be preserved when interpreting hardware results.
