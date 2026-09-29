# AUDIT20.4.5.9.36.7 — WEB/WIFI STABILITY

## Field symptom
WebUI on the STA address may be difficult/unreachable until a board reset; reset only sometimes restores access.

## Root-cause hypothesis addressed
In setup, `server.begin()` can execute while STA association/DHCP is still asynchronous. Existing WiFi recovery restores STA/IP but did not explicitly rebind the AsyncTCP listener after a real network transition. 9.36.7 adds a bounded, transition-driven rebind. This is a targeted hypothesis, not yet a hardware-proven root cause.

## Changes
- `ensureWiFi()` detects a genuine transition to usable STA+IP and publishes a one-shot atomic web-rebind request.
- Main loop consumes that request and performs `server.end(); delay(2); server.begin();`.
- Routes are NOT reset/recreated; configuration/auth/OTA state is not modified.
- Rebind is NOT timer-driven and is NOT triggered by an idle browser, so there is no periodic connection churn.
- Added `/api/net/health` lightweight read-only diagnostics: WiFi status/mode/IP/RSSI, heap/largest block, reconnect/full-restart/recovery-AP counters, STA-up count and last up/down timestamps.
- Existing WiFi recovery, AP fallback, BLE gates, CAN/RS485, BMS/SOC guards, OTA auth and PowerStream BLE logic remain unchanged.

## FMEA / fail-safe review
1. Stable STA: no extra rebind. PASS by design/simulation.
2. First DHCP completion: exactly one rebind. PASS by state model.
3. Disconnect/reconnect: exactly one rebind per recovered STA/IP transition. PASS.
4. Browser closed/idle: no rebind. PASS.
5. WiFi remains down: existing reconnect/full-restart/AP recovery continues; no web-rebind loop. PASS.
6. Rebind clears routes: NO — `end()/begin()` retains handlers; `reset()` is never called. Library implementation reviewed.
7. Safety/control regression: no CAN, BMS, SOC guard, JK proxy, PS BLE command-path changes.

## Simulation / regression
- `host_sim_web_wifi_rebind_9367.py`: 20,000,000 modeled steps; 36,580 STA-up transitions; 36,580 rebinds; 0 violations.
- `host_sim_wifi_health_recovery.py`: 10,000,000 random states; 0 false-healthy.
- `host_sim_v29_wifi_recovery.py`: 106,012 checks; 0 violations.
- `host_sim_ps_ble_lab2.py`: 10,000,000 checks; 0 violations.
- `host_sim_resource_gate.py`: 10,000,000 steps; 0 violations.
- `host_sim_final_regression.py`: 20 seeds; 12 static checks; protocol/ring/FIFO regression PASS. Test expectation updated only for 9.36.7 version string.

## Remaining verification boundary
- PlatformIO compile/link was not available in the audit environment; therefore no claim of compile verification is made.
- Physical ESP32/FritzBox/AsyncTCP behavior must be verified on hardware. The rebind mechanism addresses a strong lifecycle hypothesis but is not claimed as proven root cause until field test.
- If STA stays connected and `/api/net/health` also becomes unreachable without any up/down transition, investigate AsyncTCP/socket exhaustion, loop/task stalls, heap fragmentation, or BLE coexistence next.
