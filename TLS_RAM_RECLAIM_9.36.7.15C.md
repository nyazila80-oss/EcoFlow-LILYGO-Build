# 9.36.7.15C TLS RAM Reclaim

Pure-Arduino build; no ESP-IDF hybrid/package changes.

Targeted changes from the proven 9.36.7.13 application baseline:
- EcoFlow TLS trust remains verified, using only DigiCert Global Root G2.
- Cloud HTTPS job executes on the already-existing Arduino loop task instead of allocating a persistent 6144-byte cloud task stack.
- Dedicated 3072-byte diagnostic heartbeat task is not created in this RAM-reclaim build.
- Throw-away DNS/TCP diagnostic connection before TLS is removed to avoid pre-handshake heap fragmentation.
- WebSocket clients are closed and reconnects rejected only during the cloud TLS window, then normal WebSocket service resumes.
- Cloud write remains disabled. AccessKey/SecretKey/HMAC and EcoFlow API paths are unchanged.

Expected internal-DRAM reclaim before TLS: approximately 9 KiB of task-stack reservations plus transient WebSocket/TCP allocations, compared with the failed .14 diagnostic architecture. Exact hardware values must be measured.
