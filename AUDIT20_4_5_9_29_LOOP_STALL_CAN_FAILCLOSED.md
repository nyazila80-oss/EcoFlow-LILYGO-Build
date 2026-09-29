# AUDIT20.4.5.9.29 — LOOP-STALL CAN FAIL-CLOSED

## Finding
`BmsSafetySnapshot.valid` was invalidated by `bms.main_task()`. If Arduino `loop()` stalled, the independent CAN RX/decode tasks could continue and `sendCANFrame()` could admit replies using a still-true snapshot valid bit even after the last JK status frame exceeded the 3000 ms stale limit.

## Hardening
`bmsTelemetryValidForCan()` now independently checks both the coherent snapshot valid bit and wrap-safe age of `lastValidMs` on every CAN TX admission. This makes the central CAN TX primitive fail closed after 3000 ms even if the Arduino loop is stalled, as long as the CAN task itself is scheduled and reaches `sendCANFrame()`.

## Scope / limitation
This does not prove behavior during a total CPU scheduler freeze, interrupt lockup, hardware fault, or TWAI driver hang. It specifically removes dependence on the main Arduino loop for stale-data CAN admission.
