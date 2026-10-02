# 9.36.7.15AC3 — BLE memory lifecycle attribution

Parent: 15AB hardware baseline.

Goal: attribute the observed largest8 degradation (~42,996 -> 21,492 -> 15,348 -> 10,740 -> 7,668 B) to concrete NimBLE/PowerStream lifecycle stages and fix only proven retained resources.

## Frozen behavior
Do not change PowerStream authentication bytes, TLS/CA behavior, CAN/RS485 behavior, or heap guard thresholds in this gate.

## Attribution checkpoints
Record free heap, internal8 free, largest8 and integrity at:
1. boot before NimBLE init
2. after NimBLE init
3. after JK server/GATT/client/advertising setup
4. PS request admission
5. worker task creation
6. auxiliary-slot/reservation transition
7. PS client allocation
8. after connect
9. after service/characteristic discovery
10. after subscribe
11. before/after auth writes
12. immediately before disconnect
13. after disconnect
14. after client delete/reuse decision
15. after worker exit
16. +5 s and +30 s quiescent checkpoints

Also record bounded counts only: NimBLE client count, worker state, queue count, heavy-owner state, advertising state, JK link state. No BLE payload/auth secrets.

## Tests
- cold boot, no PS transaction baseline
- one AUTH_ONLY transaction
- three sequential AUTH_ONLY transactions with cooldown
- failed-auth path (current 0x04) cleanup
- successful path later, once auth is fixed

## Fix rule
Do not call broad NimBLE deinit/reinit merely to inflate largest8 while JK service is required. Fix only an object/lifecycle retention proven by before/after checkpoints. Verify cleanup does not break JK app proxy, callbacks, advertising, Wi-Fi/Web, CAN or RS485.

## Acceptance
After transaction cleanup, largest8 must return to a stable bounded range relative to the same-boot pre-transaction baseline, with no monotonic degradation across three transactions and heap integrity always true.