# AUDIT20.4.5.9.33 — FINAL TIMEOUT BOUNDARY HARDENED

Final re-audit of 9.32 found one concrete reassembly-ordering defect.

## Finding
`MSG14001_TIMEOUT_MS` was evaluated only after routing the newly received frame. A partial message older than 300 ms could therefore accept a late MID/END first. In the END case, if the resulting length and CRC were valid, `try_finish()` could process the stale message before the timeout reset executed.

## Fix
Expire an active partial 0x14001 reassembly before admitting each newly received frame. Time arithmetic remains uint32 wrap-safe. START then opens a clean new message. The existing post-route timeout remains as defense in depth.

## Verification actually run
- timeout-boundary adversarial model: 2,000,000 iterations; 759,598 late MID/END checks; 0 violations.
- final regression: 20 seeds; 12 static checks; PASS.
- CAN bus-off recovery: 10,000,000 checks; 0 violations.
- CAN TX boundary: 1,000,000 messages / 18,574,423 fragment checks / 866,854 aborts; 0 violations.
- BLE stream failclosed: 5,000,000 steps; 0 violations.
- BLE backpressure: 10,000,000 steps; PASS.
- resource gate: 10,000,000 steps; 0 violations.
- SOC/SOH: 3,000,000 operations; 0 violations.

No PlatformIO compiler is installed in this environment; no compile or hardware PASS is claimed.
Automatic SOC 20/25 enforcement remains OFF.
