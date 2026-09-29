# AUDIT20.4.5.9.3 – PS Priority Shared BLE Lifecycle

- Basis: 20.4.5.9.2 shared-BLE architecture.
- NimBLE remains initialized only by the existing JK proxy; PS code reuses the same stack.
- BLE max connections remains 2; PS one-shot is rejected while JK app/proxy client is connected.
- No scan and no automatic PS reconnect.
- PS notify callback only copies bounded data into a fixed queue; crypto/protobuf processing stays in worker task.
- NimBLE-Arduino pinned to 2.5.1.
- Lifecycle hardening: removed arbitrary disconnect+30 ms delay before deleteClient. NimBLEDevice::deleteClient owns disconnect/cancel and attribute cleanup in 2.5.x.
- Added per-operation heap/largest-block before/after cleanup telemetry and cleanup counter for real repeated-cycle leak/fragmentation testing.
- Existing can.cpp and low_soc_guard.cpp unchanged from 20.4.5.9.2 (and inherited safety path unchanged from 20.4.5.8).
- Host shared-BLE simulation rerun: 30,000 runs / 18,000,000 checks / 0 violations.
- PlatformIO binary compile NOT performed in this environment because pio is unavailable. Hardware/WiFi/BLE coexistence and repeated-cycle heap stability remain hardware acceptance tests.
