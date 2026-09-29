# AUDIT20.4.5.9.9 — SOC 20/25 automation FMEA / simulation-ready

Runtime automation remains OFF. This release hardens the lab path and adds a host model for the future controller.

## New source fix
9.8 tested WiFi health only when `WiFi.getMode()==WIFI_STA`. Recovery uses AP+STA, so an AP+STA state could bypass the STA-disconnected admission/cancellation test. 9.9 treats both WIFI_STA and WIFI_AP_STA as STA-enabled.

## Proposed future controller invariants
- <=20% latches block; >=25% releases it.
- While blocked, only Storage (1) may be requested.
- BMS stale/invalid: automation issues no PowerStream policy command; existing CAN fail-closed path remains authoritative.
- BLE command failure never causes policy-driven CAN silence.
- Ownership is RAM/session scoped; reboot discards restoration ownership and re-derives action from current SOC/telemetry.
- Restore only a mode actually displaced by the guard in the same boot session.

## FMEA scenarios modeled
Reboot at 18%; stale/recovery around thresholds; 19/20/21 and 24/25/26 chatter; BLE command failure; user mode changes; delayed command results; repeated block/release cycles.

## Important residual ambiguity
If the guard changed Supply->Storage and, while blocked, the user independently selects Storage in the EcoFlow app, there is no observable mode transition: both intents have the same resulting value. On release, an automatic restoration to the pre-guard Supply mode could therefore override that unobservable user intent. This cannot be solved from the observed supply-priority bit alone. Hardware/UI policy must decide whether automatic restoration is acceptable or whether explicit user ownership signalling is required.

## Safety gate
Do not enable automatic SOC control until manual hardware tests establish that Storage Priority actually stops meaningful JK-measured discharge while still allowing charging, and repeated BLE cycles do not destabilize WiFi/JK/CAN.

## New race found by the simulator
The first model immediately found a real design defect: a Supply restore can be queued after >=25%, then SOC can fall back <=20% before the delayed BLE result/commit. A naive controller can therefore transiently restore discharge while the SOC latch is blocked.

The corrected model separates desired mode from in-flight command and never launches a new Supply command while blocked. 250,000 randomized runs x 80 events = 20,000,000 invariant checks, 0 violations. It still observed 75,417 cases where a restore had been launched while allowed and the model re-entered block before that in-flight restore completed. This is not a software-invariant violation; it is a real asynchronous physical race.

### Required mitigation before runtime automation
An automatic Supply restore must carry a guard precondition and re-check it immediately before the actual PowerStream `writeValue()` (after connect/auth, not only when the worker is queued). If SOC has re-latched or BMS telemetry is stale at that point, abort the Supply write. A short resume dwell can reduce churn but does not replace the commit-time precondition. If SOC falls after the write has already been transmitted, the command cannot be unsent; the controller must mark Storage as desired and reassert it as soon as the current transaction completes. This residual transient must be included in hardware validation.
