# 9.36.7.11 Work build verification — 2026-09-25

Source: SECURITY-HARDENED-DIAG-TESTS-REFRESHED. Changes in this copy:
- Initialize four atomic BMS diagnostic counters with braces (GCC 8.4 / C++11 compatibility).
- Assign fields of queued PendingBmsOp explicitly (GCC 8.4 / C++11 compatibility).
- Pin measured espressif32 7.1.3, framework-arduinoespressif32 4.20017.260907+sha.dcc1105b, ESPAsyncWebServer 3.12.1, AsyncTCP 3.5.0, PubSubClient 2.8.0 and NimBLE-Arduino 2.5.1.

PlatformIO 6.2.0, env lilygo_tcan485: clean SUCCESS, full compilation and link SUCCESS after pins. RAM 89,348 / 327,680 bytes (27.3%); firmware program 1,540,777 / 1,835,008 bytes (84.0%). The OTA env extends this same compilation config; OTA upload was not attempted.

Host simulations: host_sim_v24_final_audit.py PASS (2,000,000 modeled operations); host_sim_final_regression.py PASS (20 seeds and all printed checks). These models do not test the actual ESP32 radio, heap fragmentation, CAN, RS485 or attached devices.

The diagnostic WebUI/API intentionally has no HTTP authentication; OTA retains password protection. Flash/use only on a trusted isolated network. No live hardware validation, A1/A2/C1/C2/D matrix, power safety confirmation, or secure release authentication closure is claimed. NimBLE compilation emitted macro redefinition warnings for BLE_MAX_CONNECTIONS and BLE_ROLE_OBSERVER; review actual effective configuration during hardware validation.
