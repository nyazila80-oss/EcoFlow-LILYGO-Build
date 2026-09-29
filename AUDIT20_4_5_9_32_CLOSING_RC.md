# AUDIT20.4.5.9.32 — Closing / Release Candidate

## Scope
Closing audit after 9.31. No feature expansion. Focus: BUS-OFF boundary across RX queue and 0x14001 reassembly, then regression closure.

## Finding fixed
9.31 prevented TX/RX while TWAI was BUS-OFF, but application RX queue entries and an in-progress 0x14001 reassembly had no fault generation. A pre-fault fragment could therefore survive long enough to be consumed after recovery and potentially share reassembly state with post-recovery traffic.

## Hardening
- Added monotonic `canBusEpoch` fault generation.
- Every transition from bus-ready to fail-closed increments the generation, including BUS-OFF, reconciliation failures/non-running states and alert-read failure boundaries.
- RX captures the epoch before blocking in `twai_receive()`.
- Application RX queue stores `{twai_message_t, epoch}`.
- Decoder rejects queued frames whose epoch differs from the current bus epoch.
- EcoFlow 0x14001 reassembly tracks the current bus epoch and resets partial state at the first frame after any fault boundary.
- No attempt is made to splice or resume a logical message across a bus fault.

## Verification actually executed
- `host_sim_bus_epoch_reassembly.py`: 100 runs, 10,000,000 steps; 4,347,655 decode checks; 804,419 stale-generation frames rejected; 237,108 boundary resets; 0 violations.
- `host_sim_can_busoff_recovery.py`: 100 runs, 10,000,000 checks, 0 violations.
- `host_sim_can_tx_boundary.py`: 1,000,000 logical messages; 18,574,423 fragment checks; 866,854 aborts; 0 violations.
- `host_sim_final_regression.py`: 20 seeds, 12 static checks; all reported counters clean.
- `host_sim_ble_stream_failclosed.py`: 5,000,000 steps; 8,114 faults; 0 violations.
- `host_sim_ble_backpressure.py`: 10,000,000 steps; PASS.
- `host_sim_resource_gate.py`: 100 runs, 10,000,000 steps, 0 violations.
- `host_sim_resource_gate_lifetime.py`: 100 runs, 10,000,000 checks, 0 violations.
- `host_sim_v26_soc_soh_hardened.py`: 3,000,000 ops, 0 violations; deterministic hysteresis/disable reset/SOH no-fake-enforcement PASS.

## Closing decision
No additional reproducible critical software finding was identified in the defined closing scope after the bus-epoch fix. Freeze this source as the software Release Candidate for hardware validation. Do not continue version churn for hypothetical improvements unless hardware testing exposes a concrete defect.

## Explicit limitations / hardware validation required
- PlatformIO is not installed in this environment: no compile/link PASS is claimed.
- No physical TWAI BUS-OFF injection/recovery test has been performed on the LILYGO/PowerStream hardware.
- No physical long-duration heap/stack soak test has been performed.
- Automatic SOC 20/25 PowerStream priority control remains OFF and is not promoted to enforced behavior.
- Same-MCU software cannot prove recovery from a complete scheduler/CPU/hardware lockup.
