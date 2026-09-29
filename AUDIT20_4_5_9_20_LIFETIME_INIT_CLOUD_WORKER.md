# AUDIT20.4.5.9.20 — Lifetime / init / cloud-worker hardening

## Findings fixed
1. Cloud worker start race: concurrent first requests could both pass `started==false` because worker creation happened before job reservation. Job reservation now occurs first; only its owner may initialize the worker. Failed worker creation releases the reservation.
2. Late CAN init race: `/can_try_init` is asynchronous and could be called concurrently, racing queue/task creation and `canTasksStarted`. CAN init/start is now serialized with a static recursive FreeRTOS mutex.
3. WebSocket ring mutexes were dynamically allocated even though rings have process lifetime and are initialized once. They now use static FreeRTOS mutex storage, removing avoidable heap allocation/failure/fragmentation.

## Safety boundaries unchanged
- Automatic SOC control remains disabled.
- BMS stale fail-closed CAN policy unchanged.
- PowerStream BLE remains one-shot/manual.
- Hardware validation and a successful PlatformIO build are still required.

## Regression rerun
- host_sim_final_regression.py: 20 seeds, 12 static checks, protocol/fifo/ring cases PASS.
- host_sim_v26_soc_soh_hardened.py: 3,000,000 operations, 0 violations; deterministic hysteresis/disable-reset/SOH-no-fake-enforcement PASS.
- host_sim_ps_ble_arbiter.py: 100,000 runs / 80,000,000 checks / 0 violations.
- host_sim_ps_ble_lab2.py: 20,000 runs / 10,000,000 checks / 0 violations.

## Remaining validation boundary
No successful PlatformIO build or hardware run was performed in this environment. Automatic 20/25 SOC control remains OFF.
