# 15O build provenance

Expected runtime marker: `9.36.7.15O-CERT-IDENTITY-CRYPTO`.

Expected filesystem marker: `2.4.5.9.36.7.15O-CERT-IDENTITY-CRYPTO`.

The dedicated GitHub Actions workflow performs a clean build of normal and OTA firmware, builds both SPIFFS images, checks the framework instrumentation and TLS verification requirement, checks firmware/filesystem provenance, compares the two SPIFFS outputs, and uploads the resulting artifacts only after all gates pass.
