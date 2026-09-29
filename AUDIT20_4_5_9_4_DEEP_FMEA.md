# AUDIT 20.4.5.9.4 — Deep FMEA / Shared-BLE Arbiter Hardening

## Scope
Deep static/concurrency/protocol review of 20.4.5.9.3 PowerStream one-shot BLE integration against the existing JK BLE proxy architecture. No claim of hardware validation or successful PlatformIO build.

## High-value findings fixed
1. **Shared BLE slot race (high):** 9.3 checked `jkBleProxyAppConnected()` only before starting the worker. The JK phone/app could connect after that check while the PowerStream client was being created. 9.4 adds an explicit auxiliary-slot reservation in `jk_ble_proxy`, stops proxy advertising while reserved, re-checks server/app/BMS state, suppresses JK reconnect contention, and restores advertising only after release.
2. **Core-link loss during PS operation (high):** 9.3 only required JK/WiFi health at admission. 9.4 makes wait/cancel logic fail closed if the JK core BLE link or STA link is lost; PS cleanup releases the slot so JK recovery can proceed.
3. **Protocol confirmation integrity (medium/high):** 9.3 accepted decrypted auth/heartbeat frames without validating the EcoFlow application frame CRC8/CRC16. 9.4 validates both before authentication or field-50 state can be accepted.
4. **Dynamic String under critical section (medium):** 9.3 copied/assigned Arduino `String` while holding a `portMUX`. 9.4 uses a fixed 128-byte error buffer inside the critical section and constructs `String` only after leaving it.
5. **Configuration/start race (medium):** asynchronous HTTP config mutation could race worker admission. 9.4 adds an atomic config admission gate and a cached atomic configured flag; config strings cannot change after worker admission.
6. **Input/NVS hardening (medium):** exact MAC syntax, bounded printable SN/UID, NVS readback verification, and strict HTTP supply mode (`"0"` or `"1"`) replace permissive `toInt()` behavior.
7. **Lifecycle observability:** status now includes notify drops, created NimBLE client count, aux reservation, heap pre/post, largest-block pre/post and cleanup count.

## Architecture invariants
- Exactly one `NimBLEDevice::init()` in project source.
- `MYNEWT_VAL_BLE_MAX_CONNECTIONS=2` remains.
- PowerStream module performs no BLE scan.
- JK app/proxy advertising is suppressed while PS owns the spare BLE slot.
- PS operation cannot intentionally coexist with a JK-app connection.
- PS failure never invokes CAN silence; BMS-stale logic remains independent.
- `src/can.cpp` and `src/low_soc_guard.cpp` are byte-identical to 20.4.5.9.3.

## Simulations / checks rerun
- Existing shared-BLE state model: 30,000 runs / 18,000,000 checks / 0 violations.
- New auxiliary-slot race model: 100,000 runs / 80,000,000 checks / 0 violations.
- Config/start admission interleaving model: 10,000,000 checks / 0 violations.
- Low-SOC atomic/failsafe model: 6,000,000 checks / PASS.
- Final regression model: 20 seeds; CAN/Jk/EcoFlow valid/corrupt/reassembly/FIFO/ring checks PASS after updating expected release marker.
- Protocol parser arithmetic fuzz: 2,000,000 random length/version/payload combinations / 0 accepted out-of-bounds cases.

## Remaining risks / not proven
- No PlatformIO compile was possible in the audit environment; `pio` is unavailable and package installation has no network access.
- NimBLE/WiFi coexistence and heap fragmentation must still be measured on the actual LILYGO hardware.
- PowerStream BLE authentication and command semantics are based on reverse-engineered behavior, not an official EcoFlow battery-control protocol specification.
- Heartbeat field 50 confirmation proves the PowerStream reports the requested priority state; it does **not** by itself prove physical battery discharge is zero. JK measured current/power remains the final physical verification.
- Automatic SOC 20/25 control remains intentionally disabled.

## First hardware-test acceptance criteria
1. JK BLE core link stays connected through PS one-shot.
2. WiFi/WebUI remains reachable throughout and for >=10 min afterward.
3. `created_clients` returns to the baseline after every PS cleanup.
4. `heap_post` and `largest_post` show no monotonic degradation over repeated cycles.
5. `notify_drops` remains zero or explainable without failed confirmation.
6. Storage command reaches CONFIRMED via CRC-valid heartbeat field 50.
7. Physical JK discharge current falls to approximately zero while charging remains possible; only then may SOC automation be considered.
