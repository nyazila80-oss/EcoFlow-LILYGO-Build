# AUDIT20.4.5.9.19 — Static mutex + guard owner hardening

## Findings fixed
1. Lazy mutex creation was race-prone in WiFi NVS, MQTT NVS, PowerStream API, cloud job state, and BMS object access. These mutexes are now statically allocated with `xSemaphoreCreate*Static`, removing check-then-create races and heap allocation from mutex creation.
2. `/api/bms/low-soc-guard` still mutated low-SOC/SOH state, ran the guard, synchronized the CAN battery snapshot, and persisted core config directly from AsyncWebServer context. It now publishes a FREE->WRITING->READY fixed-size transaction consumed by `webTick()` on the main-loop owner.
3. `saveCoreConfig()` could read live `Config` fields when invoked outside the main loop. Persistent serial/charge-voltage/CAN limits are now read from published atomic snapshots; guard settings already use atomic snapshots.

## Invariants
- Async guard POST does not directly call `setLowSocConfigAtomic`, `setLowSohConfigAtomic`, `lowSocGuardTick`, `syncCanBatterySnapshotAtomic`, or `saveCoreConfig` after queue admission.
- Only READY pending guard transactions are consumed.
- No lazy `if(!mutex) mutex=xSemaphoreCreate...` remains for the audited WiFi/MQTT/API/job/BMS mutexes.
- Automatic PowerStream SOC control remains disabled.

## Regression
- host_sim_final_regression.py: 20 seeds, 12 static checks PASS.
- host_sim_v26_soc_soh_hardened.py: 3,000,000 ops, 0 violations; deterministic hysteresis/disable reset/SOH-no-fake-enforcement PASS.
- host_sim_ps_ble_arbiter.py: 80,000,000 checks, 0 violations.
- host_sim_ps_ble_lab2.py: 10,000,000 checks, 0 violations.
- host_sim_ps_fresh_ack_physical_obs.py: 3,000,000 fresh-ACK cases + 1,000,000 physical-observation cases, 0 violations.

## Remaining validation boundary
No successful PlatformIO compile or hardware validation is claimed for 9.19. Automatic 20/25 SOC control remains OFF.
