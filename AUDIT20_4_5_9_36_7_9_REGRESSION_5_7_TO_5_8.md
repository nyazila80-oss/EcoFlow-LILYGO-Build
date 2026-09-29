# AUDIT20.4.5.9.36.7.9 — Regression audit: pre-20.4.5.8 stable baseline vs 20.4.5.8+

## Scope / evidence boundary
The workspace contains the current source and historical audit records, but not a byte-for-byte 20.4.5.7 source tree or Git history. Therefore this audit distinguishes VERIFIED DELTA (documented by release audit) from INFERRED/UNPROVEN changes. No claim of an exact source diff is made without the old tree.

## User hardware observation to explain
Pre-20.4.5.8: JK BLE + JK app + WebUI reportedly stable. Later line: WebUI becomes hard/unreachable until board power-cycle. This makes BLE itself a weak root-cause candidate and elevates regressions introduced at/after 20.4.5.8.

## Verified 20.4.5.8 delta from AUDIT20_4_5_8_HW_FAILSAFE_DIAG.txt
1. Added event-only BMS stale/recovery diagnostics with millis and last-valid age.
2. Kept EcoFlow CAN TX suppressed during recoveryPending after the first recovered JK frame; release requires the intended two-frame recovery guard.
3. Fixed /remote mobile overflow CSS/layout for diagnostics/Enforcement text.
4. No SOC/SOH threshold or JK write-policy change.
5. FW/FS manifest bumped together.

## Causality assessment
### A. JK BLE protocol path — LOW likelihood from verified 5.8 delta
No documented 20.4.5.8 change modifies JK BLE discovery, connect, notify, write, advertising, proxy queue, NimBLE init, or app-facing GATT. Therefore the historical fact that BLE was stable before 5.8 does NOT point to a direct BLE-protocol regression in the documented 5.8 delta.

### B. BMS stale/recovery diagnostics — CONDITIONAL candidate
The 5.8 diagnostics call Serial + streamDebug on stale/recovery transitions. They are event-only, not per-loop. Under a healthy RS485 stream they should be nearly dormant. Under intermittent RS485 validity, however, repeated stale/recovery cycles can add WebSocket/debug traffic and CPU/allocation pressure. This is a plausible amplifier, not yet a demonstrated root cause.

### C. recoveryPending CAN gate — SAFETY change, low direct WebUI likelihood
The two-frame recovery gate changes CAN transmit admission, not HTTP/WiFi ownership. It can increase state transitions only when BMS validity is unstable. Removing it merely to test WebUI would weaken a safety invariant and is not recommended.

### D. /remote CSS overflow fix — VERY LOW runtime likelihood
Static HTML/CSS affects browser rendering and SPIFFS payload only. It does not execute continuously on ESP32 after transfer. It is not a credible explanation for whole WebUI reachability loss unless the symptom occurs only while loading /remote and is browser-specific.

## Post-5.8 regression surface
20.4.5.9+ introduces materially larger runtime surface, especially PowerStream BLE, shared BLE arbitration/lifecycle, worker tasks, memory guards, additional diagnostics, web endpoints, and later WiFi/WebUI recovery instrumentation. These can reduce heap margin or alter scheduling even when a PowerStream command is not being sent, depending on initialization path.

## Critical distinction
"BLE OFF makes WebUI stable" would NOT prove JK BLE is defective. It could mean the added post-5.8 runtime footprint leaves insufficient heap/scheduling margin when NimBLE is present. The root cause may still be HTTP/AsyncTCP/String allocation or another post-5.8 component.

## Regression hypotheses ranked by evidence, not certainty
R1 HIGH investigation priority: aggregate heap-margin regression at/after 5.8/5.9, exposed when NimBLE is resident.
R2 HIGH: HTTP/AsyncTCP path under repeated REST polling and dynamic String JSON allocation; later firmware has substantially more diagnostics/endpoints/state.
R3 MEDIUM: repeated BMS stale/recovery events causing streamDebug/WebSocket diagnostic bursts; only relevant if RS485 validity is actually oscillating.
R4 MEDIUM: post-5.8 task/lifecycle interaction (PowerStream worker/shared BLE/resource gate/diagnostics) even without an active command.
R5 LOW: direct JK BLE protocol regression specifically in 20.4.5.8; no documented 5.8 JK-BLE delta supports it.
R6 VERY LOW: 5.8 /remote CSS change as device-side reachability cause.

## FMEA
| Failure mode | Trigger | Effect | Detection | Isolation test | Safety response |
|---|---|---|---|---|---|
| Heap fragmentation / low largest block | REST JSON + AsyncTCP + NimBLE | HTTP allocation/client failures while WiFi remains associated | free heap + largest8 + API minima + heartbeat | legacy-load A/B, BLE resident vs absent | diagnostic only; no auto reboot |
| AsyncTCP/server starvation | client churn/polling/callback pressure | IP alive, HTTP dead/slow | WiFi events remain healthy; serial alive; /api/ping fails | constant-response ping vs heavy endpoints | preserve evidence |
| RS485 stale/recovery storm | invalid/late BMS frames | diagnostic bursts + CAN gate transitions | staleEvents, recovery logs, last-valid age | count events with BLE unchanged | retain fail-closed CAN gate |
| NimBLE resident-memory pressure | JK BLE initialized | smaller heap/largest block | pre/post init heap checkpoints | A/B boot isolation | no live deinit |
| PowerStream BLE footprint | PS BLE modules initialized/worker | additional heap/task pressure | worker/memory stage diagnostics | keep PS command unused, then one-shot | bounded worker + guards |
| WiFi association loss | RF/router/driver | all HTTP unreachable | DISCONNECTED/LOST_IP reason/RSSI | serial + router status | existing reconnect/AP recovery |
| Whole-system stall | task deadlock/starvation/corruption | heartbeat stops too | independent diag task | serial observation | no diagnostic auto reboot |

## Audit decision
Do NOT remove the 20.4.5.8 two-frame recovery safety gate. Do NOT assume JK BLE is root cause. The strongest next hardware experiment is a controlled legacy-runtime-profile A/B that keeps safety semantics but suppresses nonessential post-5.8 diagnostic/web load, while preserving independent counters. A byte-exact 20.4.5.7 source/ZIP would allow a definitive source diff and should supersede inference if available.

## Verification status
Static/source-history audit: completed within available evidence.
Exact 20.4.5.7 -> 20.4.5.8 source diff: NOT possible from this workspace because 20.4.5.7 source tree/Git commit is absent.
Hardware causality: NOT yet proven.
PlatformIO compile/link: NOT performed in this environment.
