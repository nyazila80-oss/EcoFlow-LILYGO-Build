# AUDIT20.4.5.9.36.7.3 — NimBLE init admission

## Hardware evidence addressed
9.36.7.2 reported `NIMBLE BLOCK` while BMS-DATA/WIFI/HEAP/RESOURCE were otherwise OK. The runtime screenshot showed free heap ~21.1 kB and largest block ~14.3 kB. The JK/NimBLE initializer required 28 kB/12 kB after web/OTA routes were already allocated, so initialization could never start at that observed free-heap level.

## Change
- Pre-init free-heap admission threshold: 28 kB -> 20 kB. Largest-block threshold remains 12 kB.
- A pre-init low-memory condition no longer latches SAFE HOLD for the entire boot; it defers and retries later.
- All partial-allocation failures after NimBLE initialization begins remain fail-closed and latch SAFE HOLD.
- Post-client guard remains unchanged: free heap >=8 kB and largest block >=6 kB are mandatory before advertising/normal BLE operation.
- PowerStream BMS freshness, JK-app exclusion, Wi-Fi stability, resource gate, aux-owner handshake, GATT/auth and Supply SOC guards are unchanged.

## FMEA
1. Heap <20 kB or largest <12 kB: init deferred; no BLE command possible.
2. Heap later recovers: init may be retried.
3. NimBLE partial allocation fails: SAFE HOLD remains latched; no retry over partially allocated state.
4. Post-init heap <8 kB or largest <6 kB: SAFE HOLD latched before advertising/PowerStream use.
5. Concurrent JK app / pending callback events: aux reservation denied as before.
6. Stale BMS telemetry: PowerStream request rejected as before.

## Rationale
The old 28 kB threshold was stricter than the runtime state after the web stack was established. Lowering only the *entry* threshold to 20 kB allows a guarded hardware attempt while the existing post-allocation guard verifies the actual remaining memory. This does not claim 20 kB is universally sufficient; hardware compile/run is the validation boundary.
