# AUDIT20.4.5.9.16 — CONFIG VIEW / TOGGLE OWNER HARDENING

## Findings fixed
1. `/api/toggle` still mutated `Config` from AsyncWebServer context. Replaced by FREE->WRITING->READY pending transaction consumed by `webTick()` (main-loop owner). Busy concurrent mutation returns HTTP 409; accepted mutation returns HTTP 202.
2. Web status routes directly read mutable `config.*` fields while BMS/main updated them. Status now uses existing atomic CAN battery/identity snapshots, atomic message masks, atomic MOS status, and atomic misc toggle mirrors.
3. MQTT MOS/runtime publication directly read shared `config` fields. It now uses atomic snapshots/mirrors.
4. MOS status publication now has an atomic mirror updated together with the main-owned Config fields.
5. Configured CAN upper/lower limits are now separately mirrored atomically so UI does not accidentally display the low-SOC guard's effective advertised lower floor as the user's configured lower limit.
6. UI waits briefly after queued toggle before refresh, avoiding an immediate stale read after HTTP 202.

## Ownership result
AsyncWebServer no longer directly mutates the Config object. Remaining `config.*` references in web.cpp are inside `applyPendingCoreUpdate()`, called only from `webTick()` main-loop context. mqtt.cpp has no direct `config.*` field accesses.

## Tests rerun
- host_sim_final_regression.py: 20 seeds, 12 static checks PASS; 40k each protocol class; FIFO 400k; ring 240k.
- host_sim_v26_soc_soh_hardened.py: 3,000,000 ops, 0 violations; deterministic hysteresis/disable/SOH checks PASS.
- host_sim_ps_shared_ble.py: 30,000 runs / 18,000,000 checks / 0 violations.
- host_sim_ps_ble_arbiter.py: 100,000 runs / 80,000,000 checks / 0 violations.
- Toggle pending FSM model: 2,000,000 randomized scheduling steps PASS.
- Brace-balance structural check: PASS.

## Limits / not claimed
- No PlatformIO executable is available in this environment, therefore no successful firmware compile is claimed.
- No hardware validation is claimed.
- Automatic 20/25 SOC PowerStream control remains disabled.
