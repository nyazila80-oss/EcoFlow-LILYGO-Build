# 9.36.3 AUTH-WEB-STABILITY-DIAG

Scope: diagnostic/hardening follow-up to 9.36.2. No CAN/BMS/SOC/PowerStream BLE protocol behavior change.

Changes:
- HTTP Basic Auth diagnostics now include last successful-auth age and last challenge age.
- WebSocket connect/disconnect/error counters added and exposed by /api/remote/auth-status.
- BMS/PowerStream dashboard displays these counters beside existing HTTP/auth diagnostics.
- Main index WebUI network requests use bounded AbortController timeouts.
- Remote page network requests use bounded AbortController timeouts.
- PowerStream BLE Direct UI from 9.36.2 retained; SOC automation remains OFF.

Interpretation:
- Initial Basic-Auth 401 challenge is normal.
- Continuously increasing challenges after an authenticated session is established is suspicious.
- Stable auth counters with rising WS disconnect/errors or request timeouts points away from Basic Auth and toward transport/web stack stability.

Regression executed in this audit:
- FS hardening: 200,000 checks, 0 violations.
- V26 SOC/SOH: 3,000,000 ops, 0 violations; deterministic hysteresis/reset/SOH checks PASS.
- PS BLE lab2: 10,000,000 checks, 0 violations.
- BLE owner handshake: 6,000,000 checks, 0 violations.
- PS commit/compensation FMEA: 400,000 checks, 0 violations.
- Final regression: 20 seeds, 12 static checks; CAN/JK/FIFO/ring counters completed.

A real PlatformIO ESP32 build was NOT performed in this environment. User build remains required before flash.
