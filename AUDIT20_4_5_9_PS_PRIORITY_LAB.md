# AUDIT20.4.5.9 PS-PRIORITY-LAB

Manual laboratory branch only. Automatic SOC control is intentionally disabled.

Purpose: verify on the user's PowerStream that BLE supply-priority command 0x82 can switch 0=supply / 1=storage while the battery CAN link remains alive, and that storage priority physically prevents battery discharge while still permitting PV charging.

Endpoints (protected by existing remote auth / same-origin mutation policy):
- GET /api/powerstream/ble-lab/status
- POST /api/powerstream/ble-lab/config : mac, sn, uid, enabled
- POST /api/powerstream/ble-lab/supply : mode=0 or mode=1

Safety/architecture:
- No automatic SOC-triggered BLE write.
- Existing BMS-stale CAN-TX suppression is untouched.
- Existing SOC hysteresis/CAN-floor behavior is untouched.
- Credentials are write-only and persisted in NVS namespace psblelab.
- Direct BLE MAC is used; no scan is added.
- Heap guard blocks PS BLE connect if free heap <14k or largest 8-bit block <7k.
- BLE max connections raised from 2 to 3 because JK BMS client + local JK proxy server/app + PowerStream client may coexist.
- A successful BLE write is NOT considered physical enforcement. Verify heartbeat field 50 and JK current/power.
