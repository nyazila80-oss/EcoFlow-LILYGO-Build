# AUDIT20.4.5.9.36.7.2 — PSBLE BMS PATH DECOUPLING

## Root cause
9.36.7.1 incorrectly coupled PowerStream BLE admission and the auxiliary NimBLE slot to `jkBleProxyBmsConnected()`. A valid RS485 BMS path therefore could never start a PowerStream one-shot unless the unrelated physical JK-BLE central link was also connected.

## Change
- PowerStream safety health now requires `bmsTelemetryValidForCan()` (validated atomic BMS snapshot, <= 3000 ms old), not physical JK-BLE connectivity.
- Auxiliary BLE reservation still requires NimBLE initialized, JK app disconnected, no pending BLE transition, serialized owner handshake, advertising stopped/rechecked, resource gate and heap guards.
- Auxiliary reservation no longer requires physical JK-BLE connected. While reserved, JK reconnect remains suppressed by existing `sAuxReserved` logic.
- Supply retains SOC/BMS recovery guard.
- No scanning, no automatic reconnect, no automatic SOC control.
- UI labels changed from ambiguous JK/BMS-LINK to NIMBLE/BMS-DATA.

## FMEA
1. RS485 stale/invalid: request rejected before worker; worker cancellation also fails closed.
2. JK app connected/races in: reservation denied or slot-ready recheck fails.
3. Pending NimBLE callback transition: core unhealthy / reservation denied.
4. Physical JK-BLE absent: allowed if fresh RS485 BMS safety data exists; JK reconnect is suppressed during aux ownership.
5. Physical JK-BLE present: existing link may coexist; no requirement was removed for app exclusion/owner serialization.
6. Wi-Fi unstable, heap low, cooldown, heavy resource busy: unchanged fail-closed guards.
7. Supply at low SOC/recovery: unchanged fail-closed guard.
8. PowerStream connect/GATT/auth failure: unchanged cleanup and no command success claim.

## Verification
Focused state-space simulation exercises fresh/stale BMS, NimBLE init, app connection/race, pending events, reservation state, Wi-Fi and resource gate. Invariant: a PowerStream worker may reach connect only with fresh BMS data, initialized NimBLE, app-free serialized aux ownership, stable Wi-Fi, heap and resource admission.
