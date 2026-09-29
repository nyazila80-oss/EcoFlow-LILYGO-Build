# AUDIT20.4.5.9.10 — Deep FMEA / cross-core safety hardening

Scope: continuation of 9.9 audit. Automatic SOC control remains disabled.

## Findings fixed
1. **Cross-core BMS telemetry race in PS worker.** `JKPBBms` telemetry fields are ordinary fields written by the BMS parser while the PowerStream worker runs on another core. 9.8/9.9 directly sampled `bms.get_current()` during physical observation. Added a coherent atomic/seqlock `BmsSafetySnapshot` containing validity, SOC, current mA, validated-status-frame count and last-valid timestamp. The PS worker now uses only this snapshot for physical observation.
2. **Repeated cached current was counted as independent physical evidence.** The old 3 s observation sampled the same current every 100 ms even if no new JK frame arrived. 9.10 counts only a changed validated-status-frame counter and requires at least two fresh validated frames; otherwise result is `TELEMETRY_INVALID`.
3. **CAN stale gate depended on optional `battSync`.** `bmsTelemetryValidForCan()` previously returned true when battery sync was disabled even if JK telemetry was invalid, leaving a short/intentional path for CAN transmission until the guard tick set recovery-pending. 9.10 makes stale/invalid JK telemetry fail closed directly and independently of presentation/sync settings.
4. **Manual Supply could be admitted while SOC/recovery guard was active.** Admission and immediate pre-command commit checks now reject Supply when `lowSocGuardSocBlocked()` or `lowSocGuardRecoveryPending()` is true. Storage remains permitted.
5. **CAN battery seqlock had potential multiple writers.** `syncCanBatterySnapshotAtomic()` can be reached from the BMS/main path and AsyncWebServer configuration path. A seqlock assumes serialized writers. 9.10 adds a writer mux around the snapshot publication.

## Commit/compensation FMEA
New host model `host_sim_ps_commit_compensation_fmea.py` injects SOC changes, BMS invalidation, recovery, disconnects and write failures before/during Supply commit and between Supply and compensating Storage.

Result: 400,000 randomized transactions / 400,000 terminal invariant checks / 0 model violations. 14,686 paths required compensation; 126,363 became stale-contained; 360 modeled compensation writes failed. The latter is not hidden: communication failure means Storage enforcement cannot be guaranteed. In the real design this must remain an explicit FAILED/degraded state, not be relabeled as enforced.

## Existing regression rerun
- Shared BLE: 30,000 runs / 18,000,000 checks / 0 violations.
- BLE arbiter: 100,000 runs / 80,000,000 checks / 0 violations.
- LSG atomic/failsafe model: 6,000,000 checks PASS.
- Final protocol regression: 20 seeds, 12 static checks; 40,000 each valid/corrupt CAN/JK families plus FIFO/ring stress PASS.

## Remaining boundaries (not software claims)
- No successful PlatformIO compile in this environment.
- No hardware validation of 9.10.
- Storage Priority has not yet been physically proven on the user's PowerStream to inhibit discharge while preserving charge.
- A failed compensating BLE write cannot guarantee the desired PowerStream mode; this is a fundamental actuator/communications failure and must be surfaced/retried rather than disguised.
- Automatic 20/25 SOC control remains OFF.

## Release gate
Do not enable automatic SOC control until: build succeeds; manual Storage gets a fresh ACK; at least two fresh JK frames show no relevant discharge; charging is shown to remain possible; repeated BLE cycles show stable heap/stack; stale/disconnect tests preserve CAN fail-closed behavior.
