# WEB AUTH ROOT-CAUSE FMEA — 9.36.7.10 audit addendum

## Question
Could the former WebUI username/password authentication path be the root cause or an amplifier of the intermittent GUI reachability failure?

## Source facts verified
- Historical audit 9.36.2 records HTTP Basic Auth on protected pages/API and the same credentials on `/log`, `/bms`, `/debug` WebSockets via `setAuthentication()`.
- The credential was user `admin` plus a persistent password from NVS namespace `remoteauth`; password generation/NVS access happened in `remoteAuthEnsure()`.
- 9.36.3 added counters specifically because one initial browser 401 is normal but repeated challenge growth is suspicious.
- 9.36.4 deliberately removed Basic Auth from local HTTP WebUI/API and all three WebSockets while preserving OTA authentication and same-origin mutation guards.
- Current 9.36.7.10 retains the `remoteAuthRequest()` call sites but that function returns true without `authenticate()`; WebSockets likewise have no `setAuthentication()`. OTA still authenticates separately.

## Root-cause FMEA
| Failure mode | Mechanism | Expected signature | Current status / interpretation |
|---|---|---|---|
| HTTP 401 challenge/retry amplification | Browser sends unauthenticated request, receives 401, retries with Authorization | challenge counter rises; more HTTP transactions/allocations | Eliminated from normal WebUI since 9.36.4 |
| Credential-cache loss/re-prompt | browser stops/prevents preemptive Authorization | repeated 401s, apparent stalls, possibly login prompt | Eliminated from normal WebUI since 9.36.4 |
| WebSocket auth reconnect churn | WS handshake fails/challenges and JS reconnects | WS connects/disconnects/errors plus auth challenges rise | WS Basic Auth removed since 9.36.4 |
| Header/base64 parsing allocation pressure | Authorization header parsing adds transient work/allocation to every protected request | lower largest block / higher latency under high polling | no longer present in normal WebUI path |
| NVS/password initialization race | first auth request reaches password initialization while other work is active | boot/first-access correlation | `remoteAuthEnsure()` is called during `webInit`; normal WebUI admission no longer depends on it |
| Password String lifetime/corruption | invalid `c_str()` or mutation during async use | widespread/repeated auth rejection | password is static and not normally mutated after initialization; no source evidence of this fault |
| 401 + REST polling positive feedback | multiple UI pollers retry after challenge/timeouts | rising request rate/backlog before failure | plausible historical amplifier, not proven root cause |
| Auth + WS + low heap interaction | auth overhead consumes remaining heap/blocks during reconnects | failure correlated with low largest-block and auth/WS churn | plausible historical amplifier only |
| Auth removal opens LAN API | diagnostic security regression | unauthenticated LAN access | known 9.36.4+ tradeoff; OTA remains protected |

## Causal conclusion
1. **Auth cannot be the sole cause of any GUI failure that is reproducible on 9.36.4 or later**, because the normal WebUI/API and WebSocket Basic-Auth admission path is absent there.
2. Historical Basic Auth remains a credible **load amplifier/trigger**: a 401/retry or WS reconnect loop can multiply transactions and transient allocations when heap/network headroom is already low.
3. There is no source evidence that password generation, NVS storage, or the static password String itself leaks memory per request. `remoteAuthEnsure()` is not executed as a per-request normal-WebUI operation in current firmware.
4. Therefore restoring username/password into 9.36.7.10 would reduce diagnostic clarity and is not recommended for the current root-cause test.

## Model simulation
`host_sim_web_auth_rootcause_9364.py` runs 250,000 abstract UI opportunities per mode for cached-auth, intermittent auth retry, WS churn, and auth-off. It checks that auth-off cannot create auth challenges and quantifies transaction amplification in the modeled failure cases. This is a state/load model, not an ESP32/AsyncTCP timing simulation and cannot prove causality.

## Hardware discriminator if historical AUTH-ON firmware is available
Run identical UI workload on 9.36.3 AUTH-ON and 9.36.4 AUTH-OFF, with the same browser/device and no other firmware/config changes. Record auth challenge count, WS errors/reconnects, free heap, largest block, HTTP latency and time-to-unreachable. A reproducible failure only in AUTH-ON would implicate auth as trigger/amplifier. A failure in AUTH-OFF falsifies auth as a necessary cause.

## Audit verdict
**Classification: historical plausible amplifier; not supported as current sole root cause.** Keep WebUI Basic Auth removed during the present regression investigation; keep OTA authentication intact.
