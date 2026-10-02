# 9.36.7.15AC — PowerStream auth payload attribution

## Purpose
15AB established the real-hardware transport path far enough that the next gate must isolate authentication semantics instead of changing BLE transport, heap policy, or Web/UI behavior.

## Frozen baseline
Branch parent: `diag/9.36.7.15AB-ab8-memory-attribution`.

Do **not** change in this gate:
- BLE service/write/notify UUIDs
- connection/address-type policy
- callback/queue architecture
- heap admission/runtime thresholds
- command/enforcement path
- TLS/X.509 path

## Current auth construction to verify
The current implementation derives:
- AES key = MD5(SN)
- AES IV = MD5(reverse(SN))
- auth digest = MD5(UID + SN)
- auth digest encoded as 32 uppercase ASCII hex bytes
- auth command = command set `0x35`, command id `0x86`
- auth-status command = command set `0x35`, command id `0x89`

These are hypotheses until confirmed against an independent protocol reference or controlled real-hardware evidence.

## Required 15AC diagnostics (metadata only)
Never log UID, SN, derived key/IV, digest, encrypted payload, AccessKey, SecretKey, or raw auth frames.

Record only:
- UID input length
- SN input length
- concatenated auth-input length
- digest binary length (=16)
- transmitted digest representation length (=32 for current ASCII-hex path)
- auth-status frame length
- auth frame length
- protocol version / command-set / command-id as numeric metadata
- negotiated MTU
- link state immediately before/after each write
- response frame version and response/result code
- disconnect reason, if any

## Variant matrix
Do not send multiple speculative authentication attempts automatically. One explicit manual test per firmware variant.

A — baseline: `MD5(UID + SN)` -> uppercase ASCII hex (current behavior)
B — representation probe: same digest -> 16 raw binary bytes
C — ordering probe: `MD5(SN + UID)` -> uppercase ASCII hex
D — only if an independent reference justifies it; no combinatorial guessing.

Every variant must have a unique compile-time diagnostic label and preserve all safety/resource guards.

## Pass/fail interpretation
- Connect/service/write/notify/subscribe succeeds but auth response remains non-success: transport remains PASS; authentication semantics FAIL.
- A representation/order change converts the auth response to success on repeated manual tests without transport changes: candidate auth root cause found; repeat at least 3 cold boots before accepting.
- Disconnect before a response: inspect link/write/MTU metadata before attributing failure to credentials.
- No variant is accepted solely because the response code changes; require successful authenticated state and subsequent benign read/heartbeat evidence.

## Release gate
15AC is diagnostic only. Do not merge an auth variant into the release line until:
1. protocol construction is independently justified,
2. >=3 cold-boot real-hardware repetitions succeed,
3. heap/stack/callback guards remain clean,
4. no regression in Web/Wi-Fi/CAN/RS485/JK BLE coexistence,
5. secrets/raw authentication material remain absent from logs and Web diagnostics.

## Separate issue
TLS/X.509 error `-9984` is intentionally outside this gate. It must remain a separate root-cause track so a PowerStream BLE auth change cannot mask or conflate the TLS failure.
