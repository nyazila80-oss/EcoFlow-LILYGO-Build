# AUDIT20.4.5.9.28 — Resource lifetime diagnostics

## Finding
The 9.27 heavy-operation gate correctly serializes PowerStream BLE and Cloud/TLS, but had no lease-age or release-mismatch telemetry. A genuinely blocked owner therefore looked identical to a short healthy operation. Automatically stealing a timed-out lease would be unsafe because the original task may still be executing and would recreate the exact concurrent heap pressure the gate prevents.

## Hardening
- Gate now records wrap-safe acquisition age for diagnostics only.
- Acquisition counter added.
- Owner-mismatched release attempts are counted.
- No timeout-based owner stealing is implemented.
- Cloud and PowerStream BLE status JSON expose gate owner/age and mismatch telemetry.
- Task-create failure and normal completion retain explicit owner release from 9.27.
- Reboot needs no special release: ESP32 restart resets the RAM-resident atomics.

## Safety conclusion
A stuck operation may intentionally keep the gate busy. This degrades optional PowerStream BLE/cloud functions but does not permit a second heavy operation to overlap it. BMS stale/CAN fail-closed behavior is unchanged.

## Remaining hardware work
Real watchdog behavior, TLS blocking duration, BLE operation duration, stack minima and largest-free-block behavior require ESP32 hardware measurements. No timeout threshold is invented from host simulation.
