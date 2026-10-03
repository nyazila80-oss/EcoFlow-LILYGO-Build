#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# 15AO is a targeted runtime-memory fix based on the hardware evidence from
# 15AN: verified TLS reaches X.509 with ~45 KiB largest INTERNAL|8BIT before
# the handshake, but the RSA verification peak still exhausts INTERNAL/DMA.
# The WebUI already provides a safe WebSocket quiesce primitive. Close and
# clean only WebSocket clients for the short cloud transaction, then restore
# admission automatically. HTTP server, Wi-Fi, JK-BMS, CAN and TLS verification
# remain enabled. No NimBLE deinit and no insecure TLS fallback.

if '9.36.7.15AN-TLS-INTERNAL8-FIX' not in s:
    raise RuntimeError('15AO requires canonical 15AN lineage')

state='''
static std::atomic<uint32_t> g15aoWebPreFree{0},g15aoWebPreLargest{0};
static std::atomic<uint32_t> g15aoWebPostFree{0},g15aoWebPostLargest{0};
static std::atomic<bool> g15aoWebQuiesced{false};
struct Tls15aoWebGuard {
  bool active=false;
  Tls15aoWebGuard(){
    tlsInternalSnap(g15aoWebPreFree,g15aoWebPreLargest);
    webCloudQuiesceBegin();
    active=true;
    tlsInternalSnap(g15aoWebPostFree,g15aoWebPostLargest);
    g15aoWebQuiesced.store(true,std::memory_order_release);
  }
  ~Tls15aoWebGuard(){ if(active) webCloudQuiesceEnd(); }
};
'''
state_anchor='static inline void tlsInternalSnap(std::atomic<uint32_t>& freeDst,std::atomic<uint32_t>& largestDst){'
# Insert after the complete tlsInternalSnap function, using the next API_BASE declaration.
api_anchor='static const char* API_BASE = "https://api-e.ecoflow.com";'
if 'struct Tls15aoWebGuard' not in s:
    if s.count(api_anchor)!=1: raise RuntimeError('15AO API_BASE anchor missing/non-unique')
    s=s.replace(api_anchor,state+'\n'+api_anchor,1)

# Enter quiesce only after configuration/Wi-Fi checks and before constructing
# WiFiClientSecure. RAII guarantees WebSocket admission is restored on every
# early return from begin/auth/preflight/GET/error handling.
enter_anchor='''  tlsInternalSnap(gTlsInternalFreePre,gTlsInternalLargestPre);

  WiFiClientSecure client;'''
enter_new='''  tlsInternalSnap(gTlsInternalFreePre,gTlsInternalLargestPre);
  Tls15aoWebGuard tls15aoWebGuard;

  WiFiClientSecure client;'''
if 'Tls15aoWebGuard tls15aoWebGuard;' not in s:
    if s.count(enter_anchor)!=1: raise RuntimeError('15AO TLS entry anchor missing/non-unique')
    s=s.replace(enter_anchor,enter_new,1)

# Reset per-job telemetry. The reset function exists in the canonical 15AN
# build after 15AG and is deliberately reused rather than adding a second owner.
reset_anchor='''  gTlsDiagJobId.store(jobId,std::memory_order_relaxed);
  gTlsAttemptedThisJob.store(false,std::memory_order_relaxed);'''
reset_new=reset_anchor+'''\n  g15aoWebPreFree=0; g15aoWebPreLargest=0; g15aoWebPostFree=0; g15aoWebPostLargest=0; g15aoWebQuiesced=false;'''
if 'g15aoWebPreFree=0' not in s:
    if s.count(reset_anchor)!=1: raise RuntimeError('15AO reset anchor missing/non-unique')
    s=s.replace(reset_anchor,reset_new,1)

# Add compact provenance + before/after telemetry to the existing job JSON.
json_anchor=''',\\"pending\\":"+(pending?"true":"false")+'''
json_new=''',\\"15ao_web_quiesced\\":"+(g15aoWebQuiesced.load()?"true":"false")+",\\"15ao_web_pre_free\\":"+String(g15aoWebPreFree.load())+",\\"15ao_web_pre_largest\\":"+String(g15aoWebPreLargest.load())+",\\"15ao_web_post_free\\":"+String(g15aoWebPostFree.load())+",\\"15ao_web_post_largest\\":"+String(g15aoWebPostLargest.load())+",\\"pending\\":"+(pending?"true":"false")+'''
if '15ao_web_quiesced' not in s:
    if s.count(json_anchor)!=1: raise RuntimeError('15AO JSON anchor missing/non-unique')
    s=s.replace(json_anchor,json_new,1)

# Hard safety and fixed-point gates.
code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AO safety invariant: setInsecure present')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AO safety invariant: VERIFY_NONE present')
if s.count('client.setCACert(ECOFLOW_CA_BUNDLE);')!=1: raise RuntimeError('15AO CA verification cardinality != 1')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AO verified connect cardinality != 1')
if s.count('Tls15aoWebGuard tls15aoWebGuard;')!=1: raise RuntimeError('15AO guard cardinality != 1')
if s.count('webCloudQuiesceBegin();')!=1 or s.count('webCloudQuiesceEnd();')!=1:
    raise RuntimeError('15AO WebSocket quiesce lifecycle cardinality invalid')
if 'static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;' not in s:
    raise RuntimeError('15AO requires canonical 24KiB preflight')

p.write_text(s,encoding='utf-8')
print('[15AO] PASS: WebSocket quiesce RAII installed around verified TLS; HTTP/Wi-Fi/JK/CAN retained; fail-closed CA verification retained')
