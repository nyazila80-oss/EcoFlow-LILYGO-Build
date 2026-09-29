# AUDIT 20.4.5.9.36.7.6 — WEB/NETIF deep FMEA

## Scope
Static source audit of 9.36.7.5 plus 9.36.7.6 diagnostic hardening. Focus: recurring loss of HTTP/WebUI after initial successful boot, Wi-Fi/AsyncTCP/WebSocket lifecycle, heap/fragmentation, callback blocking, BLE coexistence and recovery behavior.

## Findings
1. **Server rebind is not justified by the current AsyncWebServer API.** `AsyncWebServer::begin()` delegates to the AsyncServer listener. Repeated `server.end(); server.begin();` after each STA/IP transition is an additional lifecycle transition while AsyncTCP/WebSocket clients may exist. 9.36.7.6 suppresses this rebind and retains the listener.
2. **WebSocket stale-client cleanup was incomplete before 9.36.7.5.** `/bms` was not cleaned. 9.36.7.5+ cleans `/log`, `/bms`, `/debug` once per second and keeps the low-heap extra pass bounded.
3. **Wi-Fi diagnosis previously used polling only.** `WiFi.status()` cannot explain why the station disconnected. 9.36.7.6 records STA CONNECTED/DISCONNECTED/GOT_IP/LOST_IP and the disconnect reason in atomics from the event task. No non-thread-safe recovery action is executed in the callback.
4. **Async callback heap pressure remains a credible contributor.** `/api/state` builds ~2 KiB JSON and opens Preferences namespaces inside the AsyncWebServer callback; `/api/bms` reserves 4 KiB String. This is not proven causal, but with observed free heap near ~21 KiB it increases fragmentation/transient pressure.
5. **Dependency reproducibility risk.** `ESPAsyncWebServer @ ^3.7.10` is a range, not an exact version. A future clean dependency resolution can change the web stack without source changes. Do not change library versions in this diagnostic release; pinning must be a separate A/B after recording the actual resolved versions from the user's successful compile.
6. **AsyncTCP task configuration is implicit.** No explicit `CONFIG_ASYNC_TCP_RUNNING_CORE`, queue, or stack flags are present. Current upstream documentation warns that server callback latency/queue pressure and task placement matter. Do not tune these blindly before hardware diagnostics.
7. **Wi-Fi sleep is already disabled**, reducing one common latency/reachability variable.
8. **Recovery AP is delayed 120 s.** If STA truly drops, the board should eventually expose recovery AP+STA. Failure to do so would distinguish loop/task failure from a mere HTTP listener issue.

## FMEA
| Failure mode | Existing detection | 9.36.7.6 response | Residual risk |
|---|---|---|---|
| STA disconnect / beacon loss | status + event count/reason | reconnect 10 s; full restart after 30 s | AP/router/RF cause remains external |
| STA loses IP but remains associated | LOST_IP event | normal ensureWiFi path sees unusable IP | DHCP edge case requires hardware log |
| AsyncTCP listener lifecycle disturbed by manual rebind | none previously | rebind suppressed | library-internal failure still possible |
| stale `/bms` WebSocket | client counts | cleanup every 1 s | cleanup race depends on library implementation/version |
| slow/dead browser queues | counts, cleanup | cleanup + ping | queue depth not exposed yet |
| heap fragmentation | free/largest/min heap | low-heap cleanup + BLE admission guards | HTTP String allocation still dynamic |
| Async callback stalls | HTTP latency + loop gaps | diagnostics only | callback-level timing not yet per-route |
| Preferences/NVS read inside callback | static audit | unchanged in diagnostic build | candidate for next optimization |
| BLE/Wi-Fi coexistence | PS BLE/NimBLE + Wi-Fi diagnostics | no automatic BLE action | RF coexistence requires hardware correlation |
| main-loop starvation | loop last/max gap + serial heartbeat | fail-visible | AsyncTCP task can fail independently |
| AsyncTCP queue starvation | indirect HTTP failures | no blind queue-size increase | needs serial/library debug or task metrics |
| recovery loop causes churn | reconnect/full restart counters | bounded cooldowns | repeated RF failure still churns every 30 s |
| dependency drift | static audit | documented | exact dependency pin deferred |

## Simulation
`host_sim_web_wifi_lifecycle_9376.py`: 3,000,000 randomized lifecycle states, 0 invariant violations. The model found 24,542 states where the previous rebind policy would stop/start the listener while live clients existed. This is a model exposure count, not proof of a hardware race. It also generated 279,448 stale-client/low-heap pressure states to exercise cleanup invariants.

Regression simulations retained:
- BLE owner handshake: 6,000,000 checks / 0 violations
- Resource gate: 10,000,000 steps / 0 violations
- PS BLE arbiter: 80,000,000 checks / 0 violations
- PS BLE Lab2: 10,000,000 checks / 0 violations
- PS BLE memory lifecycle: 2,000,000 runs / 0 violations

## Release decision
9.36.7.6 is a **diagnostic/hardening release**, not proof that the field failure is solved. It removes one unnecessary server lifecycle operation and adds event-level evidence. Hardware test must first run with no PowerStream BLE command. If WebUI fails, keep power on and capture router association plus Serial if available. The event counters/reason after recovery identify Wi-Fi vs HTTP/AsyncTCP vs whole-system failure.
