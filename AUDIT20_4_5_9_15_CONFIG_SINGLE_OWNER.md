# AUDIT20.4.5.9.15 – CONFIG SINGLE OWNER

Scope: AsyncWebServer -> shared Config handoff.

Findings fixed:
- `/update_param` no longer mutates `config.*` from AsyncWebServer context.
- `/api/powerstream/can-limits` POST no longer mutates local CAN limits from AsyncWebServer context.
- Fixed-size PendingCoreUpdate contains no Arduino String across task boundary.
- Three-state publication protocol FREE -> WRITING -> READY prevents consumer from seeing a reservation before payload copy is complete.
- Main-loop `webTick()` is the owner that applies the transaction, publishes CAN battery/identity snapshots, and persists relevant fields.
- Concurrent updates are rejected with HTTP 409 rather than merged nondeterministically.

New audit finding while implementing:
- A simple boolean `reserved=true` before copying the payload is unsafe: main loop can observe the reservation before the producer finishes copying. Replaced by explicit WRITING/READY publication state.

Regression:
- host_sim_final_regression: 20 seeds, 12 static checks PASS.
- host_sim_v26_soc_soh_hardened: 3,000,000 ops, 0 violations; deterministic checks PASS.
- host_sim_ps_ble_arbiter: 100,000 runs / 80,000,000 checks / 0 violations.
- host_sim_config_single_owner: 2,000,000 randomized scheduler steps / 0 violations.

Remaining audit items (not claimed fixed):
- `/toggle` still directly mutates some non-hot `config` booleans in AsyncWebServer context; CAN message enable decisions themselves use atomic mirrors, but the global Config ownership is not yet fully clean.
- Several GET/status routes read presentation fields directly from `config` while the main/BMS path may update them. They should be migrated to coherent snapshots.
- Full PlatformIO compilation and hardware validation remain outstanding.
- Automatic 20/25 SOC control remains disabled.
