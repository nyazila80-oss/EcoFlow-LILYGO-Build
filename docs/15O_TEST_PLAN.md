# 15O hardware evidence gate

15O is observation-only and keeps TLS certificate verification enabled.

After a successful clean CI build, flash the OTA firmware and matching SPIFFS image. Run exactly one PowerStream connection test, then capture `/api/powerstream/job`.

Required evidence: `tls15o_version`, `tls15m_chain`, `tls15n_verify_detail`, and `tls15o_cert_identity` for depths 0 through 3.

Analysis gate: compare leaf AKI with intermediate SKI, inspect intermediate AKI, certificate serials, signature OID bytes, public-key raw lengths, verification flags, and the existing CA trust anchor. Do not modify the trust store until this evidence is captured.
