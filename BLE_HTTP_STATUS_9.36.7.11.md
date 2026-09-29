# BLE HTTP status extension (9.36.7.11)

`GET /api/diag/ble-boot` retains its boot and heap fields. This firmware adds `diag_version`, `ble_initialized`, `app_connected` (phone to virtual JK), `real_jk_connected` (LILYGO to physical JK), `bridge_ready` (both links and no pending fault/event), `aux_reserved` (PowerStream BLE slot), `safe_hold`, `bridge_fault`, `events_pending`, `ble_startup_enabled`, connection/ready counters, last BMS disconnect reason, and BLE queue/drop/fault counters.

These fields are instantaneous read-only snapshots. Counters start at zero on reboot. `bridge_ready=true` indicates the two links are up at the instant of the request; it does not prove that JK setup data has traversed the bridge. A single response cannot prove long-run stability. The HTTP endpoint does not carry historical serial lines, credentials, BMS settings, or live CAN frames.

After the user performs an OTA firmware upload, check `diag_version` first. Observe at least two responses, including one while the JK app is connected. Expected confirmation of the full bridge is `app_connected=true`, `real_jk_connected=true`, `bridge_ready=true`; inspect `bridge_fault` and drop counters for session faults. Keep the existing partition table, SPIFFS, and NVS. No filesystem upload is required for this change.

Build target: `lilygo_tcan485_ota`. A successful local build verifies compilation/linking only; OTA and physical BLE behavior require hardware evidence.
