# FMEA / Simulation / Audit — COEX Wi-Fi modem-sleep diagnostic, 2026-09-25

## Evidence and scope
The user's COM4 monitor repeatedly showed valid 308-byte JK status frames and zero CAN drops, then an abort during JK BLE initialization at about 21 seconds. The backtrace was mapped to `coex_core_enable -> coex_enable -> esp_bt_controller_enable -> NimBLEDevice::init`. In the pinned Arduino-ESP32 framework, `WiFi.setSleep(false)` maps to `WIFI_PS_NONE`; the source had four such calls before or during Wi-Fi recovery. Espressif issue #9595 documents the same coex abort order with Wi-Fi connected, `WIFI_PS_NONE`, then NimBLE init. Causality is strongly supported but must be established on this exact board after flashing.

Compared with the previous NimBLE-config-verified ZIP, this revision changes only four `WiFi.setSleep(false)` calls to `true` in `src/wi-fi.cpp` and adds a driver-state admission check in `src/jk_ble_proxy.cpp`. The check uses `esp_wifi_get_ps`, not the Arduino cached `WiFi.getSleep`, when STA is active. It defers BLE initialization while the query fails or power save is `WIFI_PS_NONE`; no partial NimBLE allocation has occurred yet, and the one-shot `sInitAttempted` latch remains unset. A warning is rate-limited to once per five seconds.

## Failure modes
| Failure mode | Effect | Control in candidate | Residual evidence needed |
|---|---|---|---|
| Wi-Fi driver remains in `WIFI_PS_NONE` at BLE init | Coex abort/reboot loop, temporary BMS/CAN interruption | Four paths request `WIFI_PS_MIN_MODEM`; actual driver value checked before NimBLE init | COM4 log showing driver ps=1 and BLE init completes; 60+ seconds without reboot |
| `setSleep(true)` fails or cached Arduino state differs from driver | Same abort if blindly trusting cached value | `esp_wifi_get_ps` must return ESP_OK and non-NONE before init | Exercise a Wi-Fi recovery and check driver log; no repeated deferral |
| Wi-Fi restart resets power-save mode after BLE is active | Coex or WLAN instability during recovery | Every explicit STA/recovery mode transition requests modem sleep | Real AP+STA/STA reconnect, web latency, Wi-Fi counters, BLE link and heap |
| BLE init deferred indefinitely if driver reports error/NONE | JK BLE proxy unavailable; other services continue | Rate-limited warning and retry on later loop tick, no hard reboot | Diagnose exact error and Wi-Fi mode before changing gate |
| Modem sleep increases HTTP/MQTT latency or WS drops | WebUI/API responsiveness regression | Existing counters and host web/Wi-Fi simulations; no timing guarantee | Real BMS API timing/inflight, WS counts, network response under BLE activity |
| BLE memory or RF contention after coex succeeds | Low heap/fragmentation, missed CAN/BMS cycles | Existing heap admission and resource gates retained | Free/min/largest8, stack HWM, RS485/CAN and Wi-Fi/NimBLE coexistence on board |
| STA unavailable and AP only active | Driver gate is skipped; AP/BLE interaction unverified | Existing BLE heap gate retained | Separate recovery-AP hardware scenario before release |

## Host simulation and build
Nine existing host scripts passed (exit 0): `host_sim_web_wifi_rebind_9367`, `host_sim_web_wifi_lifecycle_9376`, `host_sim_ble_isolation_ab`, `host_sim_ps_shared_ble`, `host_sim_resource_gate_lifetime`, `host_sim_web_async_heap_nimble_stress_93710`, `host_sim_worstcase_lifetime_93710`, `host_sim_v24_final_audit`, `host_sim_final_regression`. They model state and allocation invariants but cannot execute the closed ESP32 radio/coex library or establish modem-sleep behavior.

PlatformIO 6.2.0 pinned environment: full clean + serial (`-j 1`) compile/link PASS on the final source. RAM 89,116/327,680 B; flash 1,539,181/1,835,008 B. A prior full-clean attempt failed because two library `.o` files were empty in this work environment; an incremental repair linked and a subsequent fresh full-clean build passed. This transient tooling issue is not an ESP32 runtime observation.

## Gates
The uploaded pre-fix run fails A1. The fixed candidate has not been uploaded or observed. Repeat A1 only: retain NVS and the compatible filesystem, flash firmware, monitor boot through JK-BLE init and at least 60 s of stable idle. Require actual driver ps value, `compiled config maxConn=2 observer=0 mtu=247`, no abort, stable Wi-Fi/IP/WebUI and JK/CAN counters, and heap/largest8/min/stack snapshots. If any item fails, capture the serial log before reboot and keep A2/C1/C2/D blocked. WebUI Basic Auth remains disabled in DIAG; OTA retains a password. Do not treat this as production release.
