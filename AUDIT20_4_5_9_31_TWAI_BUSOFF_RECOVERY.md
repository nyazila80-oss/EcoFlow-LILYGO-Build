# AUDIT20.4.5.9.31 — TWAI BUS-OFF recovery hardening

## Finding
The driver configured several TWAI alerts but no task consumed them, and BUS_OFF/BUS_RECOVERED were not enabled. A physical CAN bus-off could therefore leave the driver unable to transmit until reboot/manual intervention, while the legacy `twai_ok` flag still represented only successful installation/startup rather than current bus usability.

## Hardening
- Added BUS_OFF, RECOVERY_IN_PROGRESS and BUS_RECOVERED alerts.
- Added mandatory high-priority `canAlert` task.
- Added independent atomic `canBusReady` runtime gate; every `sendCANFrame()` requires it.
- BUS_OFF closes the gate before recovery is initiated.
- BUS_RECOVERED performs the required `twai_start()` and opens the gate only on success.
- Startup status synchronization closes the window between initial `twai_start()` and monitor task scheduling.
- 100 ms status reconciliation handles missed/coalesced alerts and retries recovery/start while remaining fail-closed.
- Core task-creation rollback closes `canBusReady`.
- Added diagnostics: bus_off, bus_recovered, recovery_fail.

## Host simulation
`host_sim_can_busoff_recovery.py`: 100 runs, 10,000,000 checks, 0 violations.

## Regression rerun in this audit turn
- `host_sim_final_regression.py`: 20 seeds, 12 static checks, PASS.
- `host_sim_v26_soc_soh_hardened.py`: 3,000,000 ops, 0 violations.
- `host_sim_ps_shared_ble.py`: 18,000,000 checks, 0 violations.
- `host_sim_ps_ble_arbiter.py`: 80,000,000 checks, 0 violations.
- `host_sim_ble_owner_handshake.py`: 6,000,000 checks, 0 violations.
- `host_sim_ble_session_epoch.py`: 20,000,000 steps, 0 violations.
- The combined long regression command timed out while starting `host_sim_ble_stream_failclosed.py`; no result is claimed for tests after that point in that command.

## Limits
No PlatformIO compile was performed because `pio` is unavailable in the environment. No hardware BUS-OFF injection/recovery test was performed. Host simulations validate modeled invariants, not ESP-IDF/TWAI hardware timing.
