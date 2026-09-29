# 20.4.5.9.36.1 PS-BLE-UI-DIAG

Basis: 9.36 WIFI-HEALTH-RECOVERY.

Changes:
- Added PowerStream BLE Direct panel to `data/bms_dashboard.html`.
- Uses the already existing authenticated endpoints `/api/powerstream/ble-lab/status`, `/config`, `/supply`.
- Manual one-shot only. No BLE scan, no periodic reconnect, no automatic SOC control.
- Storage/Supply commands retain all backend safety gates; Supply remains blocked by active low-SOC/recovery guard.
- BLE status exposes ACK/observation/current range/heap/resource-gate diagnostics already present in 9.36 backend.
- Added bounded browser fetches (4 s BMS, 5 s PowerStream API) so a stalled HTTP request cannot permanently stop UI polling.
- Added browser-side PowerStream HTTP latency/error counters. BLE status polls every 3 s only while PowerStream tab is active.
- MAC/UID are not returned by the status endpoint; UID input is password/write-only.
- No CAN/BMS/BLE backend behavior, partition table, OTA, WiFi recovery, or SOC thresholds changed.

Validation performed in this workspace:
- JavaScript syntax parse: PASS.
- Required DOM IDs unique: PASS.
- Existing BLE backend route/parameter mapping manually checked against `src/web.cpp`: PASS.
- `host_sim_ps_shared_ble.py`: 30,000 runs / 18,000,000 checks / 0 violations.
- `host_sim_ps_commit_compensation_fmea.py`: 400,000 checks / 0 violations.
- `host_sim_ble_owner_handshake.py`: 6,000,000 checks / 0 violations.
- Several longer historical host simulations exceeded the per-command execution window and are not claimed as rerun.

Real PlatformIO compile and hardware behavior are NOT claimed until built/tested by the user.
