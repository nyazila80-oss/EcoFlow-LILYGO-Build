from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 9.36.7.15H: diagnose the hardware-observed transition from TLS OOM to
# MBEDTLS_ERR_X509_CERT_VERIFY_FAILED when BLE/NimBLE is disabled at boot.
# Security invariants: CA verification stays enabled; never add setInsecure().
if 'client.setInsecure' in s:
    raise SystemExit('15H security regression: insecure TLS present')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s:
    raise SystemExit('15H invariant: CA verification anchor missing')

# time.h is part of Arduino/ESP32 and lets us expose the RTC/SNTP epoch used by
# mbedTLS certificate validity checks without touching TLS policy.
if '#include <time.h>' not in s:
    anchor='#include <Arduino.h>\n'
    if anchor not in s:
        raise SystemExit('15H include anchor missing')
    s=s.replace(anchor, anchor+'#include <time.h>\n', 1)

# Add read-only diagnostic state next to the existing TLS diagnostics.
anchor='static std::atomic<uint32_t> gTlsInternalGetPostLargest{0};'
if anchor not in s:
    raise SystemExit('15H TLS diagnostic anchor missing')
extra='''\nstatic std::atomic<int64_t> gTlsEpochPre{0};
static std::atomic<int64_t> gTlsEpochPost{0};
static std::atomic<bool> gTlsTimeSanePre{false};
static std::atomic<bool> gTlsTimeSanePost{false};
static std::atomic<uint32_t> gTlsInternalPreVerifyFree{0};
static std::atomic<uint32_t> gTlsInternalPreVerifyLargest{0};
static std::atomic<uint32_t> gTlsInternalPostVerifyFree{0};
static std::atomic<uint32_t> gTlsInternalPostVerifyLargest{0};
'''
if 'gTlsEpochPre' not in s:
    s=s.replace(anchor, anchor+extra, 1)

# Epoch >= 2024-01-01 is deliberately only a diagnostic sanity flag. It does
# not bypass or replace mbedTLS validation.
helper='''\nstatic bool tlsEpochSane(time_t t){ return t >= (time_t)1704067200; }\n'''
if 'static bool tlsEpochSane' not in s:
    pos=s.find(anchor)
    end=s.find('\n', pos+len(anchor))
    # insert after the diagnostic declarations added above
    marker='static std::atomic<uint32_t> gTlsInternalPostVerifyLargest{0};\n'
    if marker not in s: raise SystemExit('15H helper insertion marker missing')
    s=s.replace(marker, marker+helper, 1)

# Capture time and INTERNAL heap immediately before the blocking GET/TLS
# handshake and again after it returns. This distinguishes invalid clock from
# certificate/chain failure and records the TLS peak without weakening TLS.
get_anchor='gTlsInternalGetPreLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);'
if get_anchor not in s:
    raise SystemExit('15H GET pre anchor missing')
pre='''\n  const time_t tlsNowPre=time(nullptr);
  gTlsEpochPre=(int64_t)tlsNowPre;
  gTlsTimeSanePre=tlsEpochSane(tlsNowPre);
  gTlsInternalPreVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPreVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);'''
if 'const time_t tlsNowPre=time(nullptr);' not in s:
    s=s.replace(get_anchor, get_anchor+pre, 1)

# Existing code stores http.GET() in a variable; instrument directly after the
# unique call, independent of the variable name.
needle='http.GET();'
pos=s.find(needle)
if pos < 0:
    raise SystemExit('15H http.GET call missing')
if s.find(needle,pos+1) >= 0:
    raise SystemExit('15H http.GET call not unique')
post='''\n  const time_t tlsNowPost=time(nullptr);
  gTlsEpochPost=(int64_t)tlsNowPost;
  gTlsTimeSanePost=tlsEpochSane(tlsNowPost);
  gTlsInternalPostVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPostVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);'''
if 'const time_t tlsNowPost=time(nullptr);' not in s:
    s=s[:pos+len(needle)]+post+s[pos+len(needle):]

# Extend the existing status JSON. Keep this read-only and do not expose CA or
# credentials. Anchor immediately before internal_free_pre, already proven by
# the 15F gate.
json_anchor='\\"internal_free_pre\\":"+String(gTlsInternalFreePre.load())'
if json_anchor not in s:
    raise SystemExit('15H status JSON anchor missing')
fields='''\\"tls_epoch_pre\\":"+String((long long)gTlsEpochPre.load())+","+
    "\\"tls_epoch_post\\":"+String((long long)gTlsEpochPost.load())+","+
    "\\"tls_time_sane_pre\\":"+String(gTlsTimeSanePre.load()?"true":"false")+","+
    "\\"tls_time_sane_post\\":"+String(gTlsTimeSanePost.load()?"true":"false")+","+
    "\\"tls_internal_pre_verify_free\\":"+String(gTlsInternalPreVerifyFree.load())+","+
    "\\"tls_internal_pre_verify_largest\\":"+String(gTlsInternalPreVerifyLargest.load())+","+
    "\\"tls_internal_post_verify_free\\":"+String(gTlsInternalPostVerifyFree.load())+","+
    "\\"tls_internal_post_verify_largest\\":"+String(gTlsInternalPostVerifyLargest.load())+","+
    "'''
if '\\"tls_epoch_pre\\"' not in s:
    s=s.replace(json_anchor, fields+json_anchor, 1)

# Hard safety/provenance gates.
required=[
    'client.setCACert(ECOFLOW_CA_BUNDLE);',
    'gTlsEpochPre', 'gTlsTimeSanePre',
    'gTlsInternalPreVerifyFree', 'gTlsInternalPostVerifyLargest',
    'tls_failed_alloc_count', 'cred_request_secret_match'
]
for token in required:
    if token not in s: raise SystemExit('15H required token missing: '+token)
if 'setInsecure' in s: raise SystemExit('15H security regression after patch')

p.write_text(s,encoding='utf-8')
print('15H X509/time/internal-RAM diagnostics applied; CA verification remains enabled')
