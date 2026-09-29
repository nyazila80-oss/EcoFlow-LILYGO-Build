# AUDIT20.4.5.9.18 — BMS SHORT-LOCK DIAGNOSTIC SNAPSHOT HARDENING

## Findings fixed
- `/api/bms` and `/api/bms/full` held the live JKPBBms mutex while constructing multi-kilobyte JSON. This was race-safe but could delay the 800 ms JK poll/parser path under slow or repeated HTTP reads.
- `/api/remote/write-status` had the same unnecessary lock-hold pattern.
- `lowSocGuardTick()` still read the live JKPBBms object directly even though a coherent atomic safety snapshot already existed.

## Changes
- Added `bmsDiagnosticSnapshot()`: copy the plain JKPBBms state by value while holding the BMS mutex only for the bounded copy, then release immediately.
- `/api/bms`, `/api/bms/full`, and remote write-status build JSON only from the local copy. No BMS mutex is held during String allocation/formatting or HTTP send.
- Low-SOC/SOH/stale guard consumes one coherent `BmsSafetySnapshot` per tick for validity, frame generation, last-valid age, SOC and SOH.
- Automatic PowerStream 20/25 control remains disabled.

## Regression
- host_sim_final_regression.py: 20 seeds, 12 static checks PASS.
- host_sim_v26_soc_soh_hardened.py: 3,000,000 operations, 0 violations; deterministic tests PASS.
- host_sim_ps_ble_arbiter.py: 100,000 runs / 80,000,000 checks / 0 violations.
- host_sim_ps_shared_ble.py: 30,000 runs / 18,000,000 checks / 0 violations.
- host_sim_ps_ble_lab2.py: 20,000 runs / 10,000,000 checks / 0 violations.

## Remaining validation boundary
No successful PlatformIO compile or hardware timing test was available in this environment. The bounded snapshot copy materially shortens lock duration, but actual worst-case JK poll latency must still be measured on hardware under repeated `/api/bms/full` traffic.
