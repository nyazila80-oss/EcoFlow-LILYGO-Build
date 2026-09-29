# AUDIT20.4.5.9.23 — BLE init fail-closed hardening

## Finding
In 9.22 the virtual JK GATT server began advertising before the central/client object for the real JK link was allocated and before the post-client heap guard passed. If `NimBLEDevice::createClient()` failed, or the heap/largest-block guard failed immediately afterwards, `sSafeHold` latched for the boot but the virtual JK proxy remained connectable. A phone could therefore connect to a proxy that could no longer establish/maintain its required real-JK side.

## Change
Advertising is now the final externally-visible step of successful JK BLE initialization. The order is:
1. NimBLE init
2. server/service/characteristic creation
3. GATT server start
4. real-JK client allocation/configuration
5. post-client heap/largest-block guard
6. advertising object validation/configuration
7. start advertising
8. publish `sInitialized=true`

All known partial-allocation and low-memory exits before step 6 therefore leave the virtual JK non-advertised and fail closed for the boot.

## Regression
- host_sim_final_regression.py: 20 seeds, 12 static checks PASS
- host_sim_v26_soc_soh_hardened.py: 3,000,000 ops, 0 violations; deterministic hysteresis/disable-reset/SOH checks PASS
- host_sim_ps_shared_ble.py: 18,000,000 checks, 0 violations
- host_sim_ps_ble_arbiter.py: 80,000,000 checks, 0 violations
- host_sim_ps_ble_lab2.py: 10,000,000 checks, 0 violations
- host_sim_ps_fresh_ack_physical_obs.py: 3,000,000 fresh-ACK cases + 1,000,000 physical-observation cases, 0 violations
- host_sim_ps_commit_compensation_fmea.py: 400,000 checks, 0 violations

## Limits
No PlatformIO compile was possible in this environment (`pio` unavailable). No hardware validation is claimed. Automatic SOC control remains disabled.
