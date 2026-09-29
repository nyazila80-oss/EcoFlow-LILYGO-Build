# 9.36.6 Deep regression / FMEA addendum

## Scope
Source-to-source audit of 9.36.5 -> 9.36.6, with emphasis on PowerStream BLE Direct diagnostics, shared NimBLE ownership, fail-closed behavior, authentication response handling, UI polling, and regression boundaries.

## Exact code delta
Only these runtime files changed:
- include/config.h: version only
- src/powerstream_ble_lab.cpp: diagnostic atomics, auth response byte capture, stage-specific errors/status
- data/bms_dashboard.html: read-only rendering of the new diagnostic fields
No CAN, RS485, JK parser, JK BLE proxy, resource gate, SOC/SoH, Wi-Fi recovery, OTA, or automatic control logic changed.

## FMEA findings
1. BLE connect failure: fails closed before command TX; LINK remains unset; cleanup path retained.
2. GATT service/characteristic missing: fails closed with stage-specific error; no priority command can be sent.
3. Notify subscription failure: fails closed before authentication/command.
4. Auth-status write or auth write failure: fails closed; command phase is not entered.
5. Authentication rejection: raw response byte is captured atomically for diagnosis; no UID/key/packet payload is exposed.
6. Authentication timeout/no matching response: fails closed and distinguishes timeout from explicit rejection.
7. Disconnect/cancel/heap guard: pre-existing abort/cleanup logic remains in force.
8. Shared NimBLE / JK proxy: no JK proxy source changed; auxiliary slot and heavy-operation ownership remain mandatory.
9. Supply safety: SOC/BMS recovery commit-point guard is unchanged.
10. UI polling: new fields are read-only status fields; configuration edit guard from 9.36.5 remains unchanged.

## Regression/simulation results
- PowerStream BLE arbiter: 100,000 runs / 80,000,000 checks / 0 violations.
- PowerStream BLE lab2: 20,000 runs / 10,000,000 checks / 0 violations.
- Commit/compensation FMEA: 400,000 checks / 0 violations.
- Shared BLE model: 30,000 runs / 18,000,000 checks / 0 violations (process exceeded the short wrapper timeout only after printing the completed result).
- Resource gate: 10,000,000 steps / 0 violations.
- Resource lifetime: 10,000,000 checks / 0 violations.

## Test-harness issue found
`host_sim_final_regression.py` still hard-coded the 9.36.4 firmware version string. This caused its static gate to report `FW version` failure even though the production source change was intentional. The harness version expectation was updated to 9.36.6; the same 12 static predicates were then independently re-evaluated and passed 12/12. This was a stale-test failure, not a firmware regression.

## Remaining limitations / release status
- PlatformIO is not installed in this execution environment, so a real ESP32 compile/link was not performed here.
- Hardware/NimBLE timing against the physical PowerStream is not simulatable by the host models.
- Authentication semantics can only be confirmed from the real PowerStream response.
- The DELTA-2 BLE emulator is NOT implemented in this build; 9.36.6 only audits/clarifies that the existing FFE0/FFE1 advertiser is the JK proxy.

Conclusion: source-level and modeled regression risk of the 9.36.6 diagnostic delta is low and fail-closed. Hardware flash remains the required next validation boundary; this audit does not claim hardware certification.
