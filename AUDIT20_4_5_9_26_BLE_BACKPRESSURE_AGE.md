# AUDIT20.4.5.9.26 — BLE backpressure / age hardening

Changes:
- Increased each fixed BLE bridge queue from 2 to 4 ATT packets (244-byte payload cap unchanged).
- Added enqueue timestamp to every staged packet.
- Added wrap-safe 250 ms maximum queue age. An expired current-session packet is treated as a session-fatal bridge fault; the existing 9.25 fail-closed teardown then invalidates the epoch, flushes both queues and disconnects the JK link.
- Kept bridgePump bounded to at most one packet per direction per Arduino-loop call; no unbounded draining/blocking loop was introduced.
- No dynamic allocation was added to BLE callbacks.

Rationale:
A depth-2 queue was intentionally small but unnecessarily sensitive to short callback bursts. Depth 4 costs about 2 KiB total for both directions while preserving deterministic fixed memory. A queue-age deadline prevents the extra buffering from turning old commands/telemetry into delayed traffic after loop stalls.

Tests rerun:
- host_sim_ble_backpressure.py: 10,000,000 model steps PASS. Under the synthetic burst model depth 4 reduced modeled overflow faults by 50.94% vs depth 2. This is a model comparison, not a hardware probability claim.
- host_sim_final_regression.py: 20 seeds / 12 static checks PASS.
- host_sim_v26_soc_soh_hardened.py: 3,000,000 ops / 0 violations; deterministic hysteresis, disable-reset and SOH-no-fake-enforcement PASS.
- host_sim_ps_shared_ble.py: 18,000,000 checks / 0 violations.
- host_sim_ps_ble_arbiter.py: 80,000,000 checks / 0 violations.
- host_sim_ble_owner_handshake.py: 6,000,000 checks / 0 violations.
- host_sim_ble_session_epoch.py: 20,000,000 steps / 0 violations.
- host_sim_ble_stream_failclosed.py: 5,000,000 steps / 0 violations.

Limits:
- No PlatformIO compile was performed because `pio` is unavailable in this environment.
- No hardware timing/MTU test was performed.
- The 250 ms age threshold is conservative engineering policy and still needs measurement against real JK/App burst timing before being considered hardware-validated.
- notify() still does not provide an end-to-end phone delivery acknowledgement.
- Automatic SOC 20/25 PowerStream control remains OFF.
