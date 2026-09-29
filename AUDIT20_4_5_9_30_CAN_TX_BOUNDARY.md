# AUDIT20.4.5.9.30 — CAN TX boundary hardening

## Findings
1. `sendCANFrame()` waited up to 100 ms per TWAI fragment. A maximum guarded logical message can span roughly 67 classic 8-byte fragments, so a congested/non-progressing TX queue could accumulate multi-second producer blocking.
2. `sendCANMessage()` continued with later fragments after `sendCANFrame()` returned false. This can put a suffix of an already incomplete logical EcoFlow message on the bus.
3. Logical-message serialization used an unbounded `portMAX_DELAY` mutex wait. A stalled holder could therefore pin a second caller indefinitely.

## Changes
- TWAI enqueue timeout bounded to 25 ms per fragment.
- Logical message aborts immediately on the first failed/stale-rejected fragment; later fragments are never emitted.
- CAN logical-message mutex acquisition bounded to 150 ms; contention failure drops the competing message rather than blocking indefinitely.
- The existing per-fragment `bmsTelemetryValidForCan()` + recovery gate remains in `sendCANFrame()`, so BMS age/recovery is re-evaluated before every fragment.

## Safety semantics
Already-enqueued fragments cannot be recalled. Therefore this patch does not claim atomic bus delivery. It minimizes a partial message by stopping at the first known failure and relies on the existing receiver framing/CRC/reassembly rejection for incomplete messages.

## Verification
- `host_sim_can_tx_boundary.py`: 1,000,000 logical messages, 18,574,423 fragment checks, 866,854 injected aborts, 0 post-failure-fragment violations.
- `host_sim_final_regression.py`: 20 seeds / 12 static checks PASS after updating the expected version marker.
- `host_sim_v26_soc_soh_hardened.py`: 3,000,000 ops / 0 violations; deterministic hysteresis PASS; disable reset PASS; SOH no-fake-enforcement PASS.
- `host_sim_ble_owner_handshake.py`: 6,000,000 checks / 0 violations.
- Shared BLE: 18,000,000 / 0.
- BLE arbiter: 80,000,000 / 0.
- Session epoch: 20,000,000 / 0.
- Stream fail-closed: 5,000,000 / 0.
- Resource gate: 10,000,000 / 0.

No PlatformIO compile or hardware validation was performed in this environment.
