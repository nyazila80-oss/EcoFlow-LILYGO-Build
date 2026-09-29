# AUDIT20.4.5.9.24 — BLE session epoch hardening

## Findings fixed

1. Bridge packets were protected by queue flushes but were not intrinsically bound to the BLE session that produced them. A callback racing a disconnect/reconnect/overflow cleanup could therefore only be rejected indirectly by timing gates.
2. During callback-FIFO overflow recovery, the overflow flag/FIFO were cleared before `sBmsConnected`/`sAppConnected` were closed. This left a small admission window in which a callback could observe no pending event while the old session was still marked connected.
3. Local characteristic writes checked BMS connectivity but not app-session state/pending BLE transitions.

## Hardening

- Added monotonic `sBridgeSessionEpoch` and stamped every fixed bridge packet at callback admission.
- `takePacket()` forwards only packets whose epoch equals the current session epoch; stale packets are discarded fail-closed.
- Epoch advances on APP connect/disconnect, BMS connect failure/disconnect, successful new BMS session, and callback FIFO overflow recovery.
- FIFO overflow recovery now closes app/BMS callback admission while still inside the event critical section, before the event FIFO is exposed as empty.
- App writes now require app connected + BMS connected + no pending BLE transition.
- Existing queue flushes remain in place as the fast cleanup path; epoch validation is an independent second barrier.

## Verification rerun

- host_sim_final_regression.py: 20 seeds, 12 static checks PASS.
- host_sim_v26_soc_soh_hardened.py: 3,000,000 ops, 0 violations; deterministic hysteresis/disable reset/SOH semantics PASS.
- host_sim_ble_owner_handshake.py: 6,000,000 checks, 0 violations.
- host_sim_ble_session_epoch.py: 20,000,000 randomized steps, 483,514 deliberately retained stale packets rejected, 0 violations.
- host_sim_ps_shared_ble.py: 18,000,000 checks, 0 violations.
- host_sim_ps_ble_arbiter.py: 80,000,000 checks, 0 violations.
- jk_ble_proxy.cpp brace smoke check: PASS.

## Limits

No PlatformIO executable is available in the audit environment, therefore no successful firmware compile is claimed. No physical BLE/JK/PowerStream hardware validation is claimed. Automatic SOC 20/25 PowerStream control remains disabled.
