# AUDIT20.4.5.9.36.7 FS VERSION FIX

Corrected `data/fs_version.txt` to exactly match the firmware version in `include/config.h`.

Root cause of `FS_VERSION_MISMATCH` in the first 9.36.7 package: the filesystem marker was inherited from 9.36.4 while firmware had already been bumped to 9.36.7.

A production-path scan of `include/`, `src/`, `data/`, `platformio.ini`, and `partitions.csv` found no remaining exact stale 9.36.4 version marker after this correction.

No runtime CAN/BMS/BLE/Wi-Fi logic was changed by this correction; only the filesystem version marker and this audit note were changed.
