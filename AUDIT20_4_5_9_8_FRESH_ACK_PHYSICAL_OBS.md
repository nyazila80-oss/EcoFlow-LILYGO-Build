# AUDIT20.4.5.9.8 — Fresh ACK + physical-current observation

## Scope
Manual PowerStream BLE laboratory path only. Automatic SOC control remains disabled.

## Changes
- Added callback-stamped command epoch to every queued PowerStream notification.
- Command epoch advances only after the supply-priority `writeValue()` has returned.
- ACK requires: new heartbeat generation, requested mode match, and heartbeat packet epoch == current command epoch.
- This closes the stale-heartbeat race even when old/new packets share the same `millis()` tick.
- Added explicit observation states: REQUESTED, ACKNOWLEDGED, OBSERVING, OBSERVED_NO_DISCHARGE, OBSERVED_DISCHARGE, TELEMETRY_INVALID.
- For Storage mode only, after a fresh ACK the worker observes JK current for 3 s. Current below -0.50 A is classified as observed discharge. This threshold is diagnostic only and is NOT a validated safety limit.
- Supply mode is only ACKNOWLEDGED; no physical discharge claim is made.
- Added heartbeat/command epochs, observation sample count and current extrema to status JSON.

## Safety interpretation
`OBSERVED_NO_DISCHARGE` means only that no JK sample crossed the diagnostic discharge threshold during the observation window. It does not prove causality, future enforcement, or that PowerStream will remain non-discharging. Automatic 20/25% SOC enforcement remains disabled.

## Simulation
- Fresh ACK epoch model: 3,000,000 randomized cases, 0 violations.
- Physical observation classifier: 1,000,000 randomized cases, 0 violations.
- Existing shared-BLE simulation: 30,000 runs / 18,000,000 checks / 0 violations (previous rerun on same code line before 9.8 PS-only patch; PS-only patch does not alter arbiter).
- Existing PS state model: 20,000 runs / 10,000,000 checks / 0 violations (previous rerun; new fresh-ACK model tested separately above).
- Existing arbiter model: 100,000 runs / 80,000,000 checks / 0 violations (previous rerun; arbiter source unchanged).

## Core fail-safe hashes
- src/can.cpp: 01d7454b75b1ac3be5310644b27ddf15c61759ac7474bce0bff686e9a24f971c
- src/low_soc_guard.cpp: 2cc9ba0ef1a444742edb69ef9ca1556dd679d3596cfdd5bc6b6dfffd959edf56

Both are unchanged from 20.4.5.9.7.

## Remaining gates
1. Real PlatformIO/NimBLE-Arduino 2.5.1 build not verified in this environment.
2. Real PowerStream Storage Priority behavior not yet verified on hardware.
3. `OBSERVED_NO_DISCHARGE` must not be promoted to ENFORCED until hardware tests demonstrate repeatable zero/near-zero discharge while charging remains possible.
4. Long-run WiFi/BLE/heap/stack behavior still requires hardware cycling.
