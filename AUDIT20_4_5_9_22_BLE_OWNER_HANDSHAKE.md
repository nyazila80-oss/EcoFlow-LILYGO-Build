# AUDIT20.4.5.9.22 — BLE owner handshake hardening

## Scope
Continuation of 9.21: JK proxy / PowerStream shared-BLE arbitration, NimBLE advertising ownership, cross-task server access, reservation timeout/interleavings.

## Findings fixed
1. `jkBleProxyReserveAuxConnection()` was called by the PowerStream worker and directly invoked `NimBLEDevice::stopAdvertising()` (and failure recovery could call `startAdvertising()`). This violated the intended single-owner model used for restart.
2. `jkBleProxyAuxSlotReady()` called `NimBLEServer::getConnectedCount()` from the auxiliary worker, leaving a cross-task live NimBLE object read after advertising ownership was otherwise serialized.

## Changes
- Added atomic `AuxReserveState`: IDLE -> REQUESTED -> GRANTED/DENIED.
- Auxiliary worker only publishes REQUESTED and waits (bounded 750 ms, wrap-safe timeout).
- `jkBleProxyTick()` is the sole owner of JK-proxy `startAdvertising()` / `stopAdvertising()` during arbitration.
- Owner stops advertising, then re-checks server connection count, app state, BMS state and pending callback events before publishing GRANTED.
- Timeout withdrawal uses CAS so it cannot overwrite a concurrently committed GRANTED/DENIED result.
- Release publishes IDLE and defers advertising restart to `jkBleProxyTick()`.
- Worker-visible `jkBleProxyAuxSlotReady()` now uses atomic/event snapshots only; no live `NimBLEServer` method call.

## Verification rerun
- New abstract owner-handshake adversarial model: 100 runs, 6,000,000 checks, 0 violations.
- `host_sim_final_regression.py`: 20 seeds, 12 static checks, protocol/ring/FIFO regression PASS.
- `host_sim_v26_soc_soh_hardened.py`: 3,000,000 ops, 0 violations; deterministic hysteresis/disable-reset/SOH checks PASS.
- `host_sim_ps_shared_ble.py`: 18,000,000 checks, 0 violations.
- `host_sim_ps_ble_arbiter.py`: 80,000,000 checks, 0 violations.
- `host_sim_ps_ble_lab2.py`: 10,000,000 checks, 0 violations.
- `host_sim_ps_fresh_ack_physical_obs.py`: 3,000,000 fresh-ACK cases + 1,000,000 physical-observation cases, 0 violations.

## Remaining limitations
- PlatformIO (`pio`) is not installed in this runtime; no successful firmware compile is claimed.
- No hardware BLE timing/connection-stress validation is claimed.
- Automatic SOC 20/25 PowerStream control remains OFF.
- Next audit target: callback FIFO overflow recovery, bridge queue/session epochs, disconnect/reconnect event storms, and failure injection around BLE resource creation.
