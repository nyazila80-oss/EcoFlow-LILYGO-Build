# AUDIT18.7 implementation notes

This revision hardens the JK-PB V19 write path. A setting write is not considered successful merely because bytes were transmitted. The firmware now waits for the standard 8-byte Modbus FC10 acknowledgement, validates its CRC and echoed register/count, then requests the 0x161E settings block and compares the returned raw little-endian UINT32 with the requested value.

For first hardware validation, high-impact controls are deliberately locked: device address, charge MOS, discharge MOS, balancer enable, and function bits. They remain readable. The allow-list keeps numeric protection/configuration values plus precharge and smart-sleep.

PowerStream CAN local SOC limits remain independent of EcoFlow cloud/API. Defaults are 100% upper and 10% lower. CB/2031 and CB/2033 remain observation/response paths, not claimed persistent-setting writes.

AUDIT19.15.1 diagnostic-safe consolidation (based on 19.14 crash-log hardening):
- 19.13 async NimBLE connect reverted after hardware abort immediately after link-up.
- CAN application RX queue reduced 256 -> 64 to recover internal heap.
- BLE fail-closed heap guards added (28k before NimBLE init, 8k before client connect).
- Large JK raw frame dumps disabled by default; bounds review found guarded frame/raw writes.

## AUDIT19.15.36 — CROSS-CORE STATE GUARD
- `sBmsConnected` and `sAppConnected` are now `std::atomic_bool` because NimBLE host callbacks and the Arduino loop access them from different execution contexts.
- Callback-side characteristic pointer reads were removed where unnecessary; remote/local characteristic dereferences remain in the serialized loop-side bridge pump.
- Existing event and bridge queues remain protected by ESP32 critical sections.
- V13 host model: 5,000,000 randomized lifecycle/interleaving events, zero callback pointer dereferences, source invariants 7/7.
- No JK protocol, RS485 parser, battery protection settings, EcoFlow CAN payload, or SOC limit changes.
- Static/host-tested only; not compiled with PlatformIO or tested on ESP32 hardware in this environment.

## AUDIT20.4.3 RAW-CB-FORENSIC
20.4.2 logical-message recorder replaced by a raw CAN forensic recorder. See AUDIT20_4_3_RAW_CB_FORENSIC.txt.

## AUDIT20.4.4.4 CONFIG/NVS HARDENED
- Atomic CAN TX gate and atomic EcoFlow message-enable mask.
- Removed shared global Preferences handle; persistence uses local handles per operation.
- Added `host_sim_v20_config_nvs_hardened.py` (4,000,041 checks PASS).
- Low-SOC guard remains monitor-only pending verified DCL mapping.

## AUDIT20.4.5.7 FINAL-DEEP-HARDENED
- Re-audited from the full 20.4.5.6 project baseline, not only the delta.
- WebUI delivery now fails closed on FS_VERSION_MISMATCH (HTTP 503); mismatched SPIFFS HTML is not served.
- Recovery/setup AP no longer uses the shared fixed password `ecoflow123`; it uses the device-specific WebUI admin secret.
- Historical BLE regression version gates updated to the current release so functional failures are no longer hidden by stale version assertions.
- Added host_sim_v31_release_deep_hardening.py for release/FS/auth/partition invariants.
- No guessed PowerStream DCL/0-W CAN command was added. Physical 0-W enforcement for SOH/BMS-stale remains a hardware/protocol verification item.

## 20.4.5.9.1 LAB2 hardening
PowerStream BLE is now manual one-shot only: no scan, no periodic reconnect, bounded worker operation, heap/WiFi admission guards, cleanup and cooldown. See AUDIT20_4_5_9_1_PS_PRIORITY_LAB2.md.
