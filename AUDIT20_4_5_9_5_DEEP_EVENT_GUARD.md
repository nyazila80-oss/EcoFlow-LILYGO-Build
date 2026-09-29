# AUDIT20.4.5.9.6 — Shared BLE event/lifetime guard

Deep audit after 20.4.5.9.4.

## New finding fixed
The JK proxy deliberately defers NimBLE connect/disconnect callbacks into a fixed event FIFO. Therefore `sBmsConnected` / `sAppConnected` can briefly describe the previous session while a transition is pending. The 9.4 auxiliary-slot predicate did not include this pending-event state. 9.5 exports a read-only `jkBleProxyEventsPending()` predicate, includes it in `jkBleProxyAuxSlotReady()`, and makes the PowerStream worker's `coreHealthy()` fail closed while any JK BLE transition is pending.

## Stack/lifetime diagnostics
The PS one-shot worker now records FreeRTOS stack high-water mark in bytes and operation age. These are diagnostic only and do not alter CAN/BMS fail-safe behavior.

## Simulation
- Existing shared-BLE model: 30,000 runs / 18,000,000 checks / 0 violations.
- Existing SOC/SOH guard model: 3,000,000 operations / 0 violations.
- New deferred-event interleaving model: 50,000 runs / 18,000,000 invariant checks / 0 violations (at the next modeled worker health checkpoint).
- Exactly one `NimBLEDevice::init()` remains in src.
- `src/can.cpp` and `src/low_soc_guard.cpp` are byte-identical to 20.4.5.9.4.

## Remaining non-simulated risks
1. No PlatformIO compile was possible in this environment; API/ABI compatibility is not claimed as compile-verified.
2. Synchronous NimBLE GATT calls can occupy the PS worker until the library/ATT timeout returns. The worker is low-priority and isolated, but a stuck library call cannot safely be force-killed by application code.
3. RF coexistence, actual heap fragmentation, and real task stack margin require hardware measurement.
4. Heartbeat confirmation of Supply Priority is not yet proof of physical zero discharge; JK measured current remains the final hardware truth for future automatic SOC enforcement.
