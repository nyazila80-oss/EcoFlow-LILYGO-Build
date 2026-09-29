# TLS Preflight / WebSocket Owner Diagnostic

Basis: TLS-MEMORY-ISOLATION-DIAG hardware trace: GET failed with TLS -32512, free heap 30.8-34.5 kB and largest 8-bit block 13.3 kB.

## Change
Before constructing WiFiClientSecure, capture allocator state, run one bounded cleanupClients() pass for all three WebSocket endpoints, wait 20 ms, then capture allocator state again. Also report INTERNAL free/largest, free/allocated block counts and minimum free bytes. BLE/JK/CAN/WiFi are not stopped or reinitialized. TLS CA validation and read-only cloud policy are unchanged.

## New /api/powerstream/job fields
pre_heap_before, pre_largest_before, pre_heap_after_ws, pre_largest_after_ws, pre_internal_free, pre_internal_largest, pre_free_blocks, pre_allocated_blocks, pre_min_free.

## Interpretation
If pre_largest_after_ws rises materially versus pre_largest_before, stale WebSocket/AsyncTCP state is contributing to fragmentation. If it does not, WebSocket cleanup is not the primary owner and the next A/B should isolate NimBLE/JK without changing TLS policy.
