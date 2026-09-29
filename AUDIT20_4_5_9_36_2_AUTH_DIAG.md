# 9.36.2 PS-BLE-AUTH-DIAG

Purpose: determine whether HTTP Basic Authentication contributes to intermittent WebUI reachability while retaining the 9.36.1 PowerStream BLE UI.

Findings from source audit:
- WebUI HTTP user is fixed to `admin`.
- A 20-character password is persisted in NVS namespace `remoteauth`, key `password`.
- If NVS cannot provide a password, firmware generates an in-RAM random password for that boot (fail-closed).
- Protected pages and API endpoints use HTTP Basic Auth.
- WebSocket handlers use the same user/password through `setAuthentication()`.
- ArduinoOTA uses the same secret as its OTA password.
- A normal browser can generate an initial 401 Basic-Auth challenge; repeated challenge growth after login is the diagnostic signal, not a single 401.
- No evidence in source proves authentication is the root cause of WebUI instability.

Changes:
- Added atomic HTTP auth success/challenge counters.
- Added authenticated `/api/remote/auth-status` endpoint. It exposes counts and password length, never the password.
- PowerStream tab displays client-side 401 count plus ESP auth OK/challenge counters.
- Remaining direct BMS dashboard mutation fetches now use bounded fetch timeouts.
- No CAN, BMS, PowerStream BLE protocol, SOC automation, WiFi recovery, OTA partition or safety behavior changed.
