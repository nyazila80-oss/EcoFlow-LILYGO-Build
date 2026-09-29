# AUDIT20.4.5.9.14 — Cloud/NVS concurrency FMEA

## Findings fixed
1. EcoFlow cloud operations were executed directly inside AsyncWebServer callbacks. `powerStreamApiSetLimits()` can block for ~15 s while waiting/verifying, risking starvation of the async networking task. Cloud test/read/set are now queued to a dedicated low-priority worker; web callbacks return HTTP 202 and the dashboard polls `/api/powerstream/job`.
2. Cloud credential/state Strings and `psApiState` could be accessed by concurrent web requests. A recursive API transaction mutex serializes credentials and synchronous cloud transactions; web no longer reads `psApiState` directly.
3. First cloud-job queue design had a TOCTOU admission race and a transient false-DONE window between `pending=false` and `running=true`. A CAS-based `gJobReserved` owns the entire job lifecycle; DONE is derived from reservation release, not the pending/running gap.
4. `/reboot` previously called delay/MQTT disconnect/restart in the AsyncWebServer callback. It now only sets an atomic request; main-loop `webTick()` performs MQTT disconnect/restart.
5. WiFi and MQTT multi-key NVS updates could overlap same-namespace readers/writers. Shared namespace mutexes now serialize each multi-key transaction. MQTT save performs NVS readback before requesting main-loop runtime reload; port is validated 1..65535.

## Tests rerun
- `host_sim_final_regression.py`: 20 seeds, static checks 12, protocol/FIFO/ring suites PASS.
- `host_sim_ps_shared_ble.py`: 30,000 runs / 18,000,000 checks / 0 violations (9.13 base; no BLE changes in 9.14).
- `host_sim_ps_ble_arbiter.py`: 100,000 runs / 80,000,000 checks / 0 violations (9.13 base; no BLE changes in 9.14).
- `host_sim_v19_lsg_atomic_failsafe.py`: 6,000,000 checks PASS (9.13 base; no guard changes in 9.14).
- `host_sim_cloud_job_fsm.py`: 1,000,000 runs / 4,000,000 checks / 0 violations.
- Structural brace checks passed for modified C++ files.

## Safety-core hashes
- `src/can.cpp`: 01d7454b75b1ac3be5310644b27ddf15c61759ac7474bce0bff686e9a24f971c
- `src/low_soc_guard.cpp`: 2cc9ba0ef1a444742edb69ef9ca1556dd679d3596cfdd5bc6b6dfffd959edf56

## Still open / next audit target
The legacy `/update_param` AsyncWebServer handler still writes several `config.*` runtime fields directly (voltage, charge voltage, temperature, SOC, runtimes, CAN limits, serial) and calls snapshot/persistence helpers from the async task. This is the next cross-core ownership issue to remove. The local CAN-limit mutation route also deserves the same single-owner treatment. Therefore 9.14 is not declared the final audited release.

No successful PlatformIO compile or hardware validation is claimed for this release.
