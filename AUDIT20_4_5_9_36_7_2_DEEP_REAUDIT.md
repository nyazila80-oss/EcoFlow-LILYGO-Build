# AUDIT20.4.5.9.36.7.2 — DEEP RE-AUDIT

## Finding corrected during re-audit
The backend semantics had correctly been decoupled from the physical JK-BLE link, but the WebUI still rendered the legacy labels `JK` and `BMS-LINK`. This was diagnostic-only but misleading. The labels are now `NIMBLE` and `BMS-DATA`. JSON field names remain unchanged for compatibility; their semantics are documented by the backend: `pre_jk_init` = NimBLE initialized, `pre_bms_link` = `bmsTelemetryValidForCan()`.

## Safety path verified
- Admission requires enabled/configured, no worker, cooldown clear, NimBLE initialized, fresh validated BMS telemetry, JK app disconnected, stable STA, heap guard, and heavy-op ownership.
- `bmsTelemetryValidForCan()` uses the atomic BMS safety snapshot and rejects invalid/zero timestamp or age > `JK_DATA_STALE_MS` (3000 ms).
- Worker `cancelled()` re-checks fresh BMS telemetry, pending BLE transitions, aux-slot readiness and STA connectivity throughout waits.
- Aux reservation no longer requires a physical JK-BLE link, but still serializes advertising ownership, rejects JK-app connection/pending events, and suppresses JK reconnect while reserved.
- Supply retains low-SOC/recovery guard. No auto reconnect or auto SOC control added.

## Focused simulations rerun
- host_sim_ps_ble_lab2.py: 10,000,000 checks / 0 violations.
- host_sim_ps_ble_arbiter.py: 80,000,000 checks / 0 violations.
- host_sim_resource_gate.py: 10,000,000 steps / 0 violations.
- host_sim_ble_owner_handshake.py: 6,000,000 checks / 0 violations.
- host_sim_wifi_health_recovery.py: 10,000,000 random states / 0 false-healthy.
- Reduced exhaustive admission/worker invariant: 1,024 states / 0 violations.

## Limitation
No local PlatformIO executable is installed in the audit container, so compile/link remains to be verified on the target user's PlatformIO environment. Hardware behavior, PowerStream GATT/auth acceptance, and RF coexistence require the real-device test.
