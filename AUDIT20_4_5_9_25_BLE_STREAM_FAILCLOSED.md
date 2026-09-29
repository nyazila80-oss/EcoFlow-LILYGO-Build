# AUDIT20.4.5.9.25 — BLE stream fail-closed hardening

## Finding
The JK BLE proxy is a transparent stream bridge. A full two-slot staging queue, an oversized ATT value, or a failed remote `writeValue()` previously dropped one packet and then continued forwarding later packets. If a JK application frame spans ATT packets, this can leave the peer parser mid-frame and allow subsequent bytes to be interpreted in the wrong framing context.

## Hardening
- Queue overflow and oversized bridge packets publish a session-fatal bridge fault.
- Failed App→BMS `writeValue()` publishes the same fault.
- The Arduino-loop owner consumes the fault, advances the bridge session epoch, flushes both bridge queues, invalidates the remote characteristic, and disconnects the real JK client.
- Forwarding and JK reconnect stay latched off until an APP_DISCONNECT event establishes a clean phone-side session boundary. The next phone reconnect starts from a clean epoch.
- NimBLE callbacks remain allocation-free and do not perform disconnect operations.
- MTU staging remains 244 bytes (ATT MTU 247 minus 3-byte ATT header). No fragmentation/reassembly behavior is invented.

## Limits
`NimBLECharacteristic::notify()` in this code path does not provide a checked delivery result, so successful notification delivery cannot be proven by firmware. The fail-closed change therefore covers detectable local drops/oversize and remote write failure, not RF-level confirmation of a phone notification.

Automatic SOC control remains OFF. No PlatformIO compile or hardware validation is claimed by this audit.
