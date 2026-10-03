#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root = Path(env['PROJECT_DIR'])
api = root / 'src' / 'powerstream_api.cpp'
ble = root / 'src' / 'powerstream_ble_lab.cpp'
p = api.read_text(encoding='utf-8')
b = ble.read_text(encoding='utf-8')

# 15AG is a source transform. PlatformIO executes pre-scripts again for later
# targets in the same checkout, after 15AH..15AN have already transformed the
# source. Never try to reconstruct an old 15AG text anchor from downstream
# source. Instead, accept it only when the complete 15AG contract is still
# provably present and the provenance is an explicitly known descendant.
version_re = re.compile(r'tls15z_version\\\":\\\"([^\\\"]+)')
versions = version_re.findall(p)
downstream = {
    '9.36.7.15AH-EARLY-TLS-HANDSHAKE',
    '9.36.7.15AI-PS-BLE-RECLAIM-DIAG',
    '9.36.7.15AK-TLS-ALLOC-PEAK-DIAG',
    '9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX',
    '9.36.7.15AM-PREFLIGHT-AB-24K',
    '9.36.7.15AN-TLS-INTERNAL8-FIX',
}

if len(versions) == 1 and versions[0] in downstream:
    failures = []
    def require(name, ok):
        if not ok:
            failures.append(name)

    # Security must remain fail-closed.
    code = re.sub(r'//[^\n]*|/\*.*?\*/', '', p + '\n' + b, flags=re.S)
    require('CA_VERIFY', 'setCACert(ECOFLOW_CA_BUNDLE)' in p)
    require('NO_SETINSECURE', 'setInsecure(' not in code)
    require('NO_VERIFY_NONE', 'MBEDTLS_SSL_VERIFY_NONE' not in code)

    # 15AG resource/lifecycle contract.
    require('BLE_RECLAIM_FN', b.count('bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)') == 1)
    require('BLE_RECLAIM_CALL', p.count('bool psBleReleased=false;') == 1)
    require('NO_NIMBLE_DEINIT', 'NimBLEDevice::deinit' not in code)
    require('JOB_RESET', p.count('resetTlsDiagnosticsForJob(n)') == 1)
    require('TLS_ATTEMPT_MARK', p.count('gTlsAttemptedThisJob.store(true') == 1)
    require('TLS_JOB_ID_JSON', 'tls_diag_job_id' in p)
    require('TLS_ATTEMPT_JSON', 'tls_attempted_this_job' in p)
    require('QUIET_WINDOW', p.count('gCloudNotBeforeMs.store(millis()+750U') == 1)
    require('QUIET_JSON', p.count('http_quiet_window_ms') == 1)
    require('FRAG_SNAP', p.count('tls15agFragSnap(') == 3)
    require('FRAG_JSON', 'frag_psram_total' in p and 'frag_queue_largest' in p)

    # 15AM/15AN intentionally own the later 24 KiB A/B threshold. Do not
    # rewrite it to 32 KiB here.
    thr24 = 'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
    thr32 = 'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
    require('DOWNSTREAM_THRESHOLD', p.count(thr24) == 1 and p.count(thr32) == 0)

    if failures:
        raise RuntimeError('15AG downstream fixed-point invariant failed: ' + ', '.join(failures))
    print('[15AG-GUARD] downstream fixed point verified; lineage=%s; no legacy re-transform attempted; CA verification retained' % versions[0])
else:
    # Native/earlier lineage: run the original 15AG transform unchanged.
    legacy = root / 'tools' / 'platformio_tls15ag_peak_fix.py'
    src = legacy.read_text(encoding='utf-8')
    exec(compile(src, str(legacy), 'exec'), globals(), globals())
