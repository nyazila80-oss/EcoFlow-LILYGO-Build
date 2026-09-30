#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 15I is intentionally additive after 15H. Never weaken TLS verification.
def executable_set_insecure(text: str) -> bool:
    for line in text.splitlines():
        code=line.split('//',1)[0]
        if 'setInsecure(' in code and not code.lstrip().startswith(('#','"',"'")):
            return True
    return False

if executable_set_insecure(s): raise SystemExit('15I security regression: executable setInsecure')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s: raise SystemExit('15I CA anchor missing')
if 'gTlsEpochPre' not in s or 'gTlsInternalPostVerifyLargest' not in s: raise SystemExit('15I requires 15H first')

# Runtime provenance visible in /status JSON. The Arduino TLS layer owns the
# mbedTLS ssl context, so this patch records the exact secure-client error and
# classifies the observed X509 failure without inventing a second verifier.
anchor='static std::atomic<uint32_t> gTlsInternalPostVerifyFree{0};\nstatic std::atomic<uint32_t> gTlsInternalPostVerifyLargest{0};'
extra='''\nstatic std::atomic<int32_t> gTls15iLastError{0};\nstatic std::atomic<bool> gTls15iX509VerifyFailed{false};\nstatic std::atomic<bool> gTls15iCaVerificationEnabled{true};\nstatic const char* TLS15I_VERSION="9.36.7.15I-X509-ROOTCAUSE";\n'''
if anchor not in s: raise SystemExit('15I atomic anchor missing')
if 'gTls15iLastError' not in s: s=s.replace(anchor,anchor+extra,1)

# Anchor to the canonical WiFiClientSecure::lastError read in the transport
# failure path. 15D currently names these tlsCode/tlsReason. Keep the older
# tlsErr spelling as compatibility only so the patch remains deterministic
# across the immediately preceding diagnostic revisions.
needles=[
    'const int tlsCode=client.lastError(tlsReason,sizeof(tlsReason));',
    'const int tlsErr = client.lastError(tlsErrBuf, sizeof(tlsErrBuf));',
    'int tlsErr = client.lastError(tlsErrBuf, sizeof(tlsErrBuf));',
]
needle=next((n for n in needles if n in s),None)
if needle is None: raise SystemExit('15I client.lastError anchor missing')
var='tlsCode' if 'tlsCode=' in needle else 'tlsErr'
add=f'''\n    gTls15iLastError.store({var},std::memory_order_relaxed);\n    gTls15iX509VerifyFailed.store({var}==-0x2700 || {var}==-9984,std::memory_order_relaxed);'''
if 'gTls15iLastError.store' not in s: s=s.replace(needle,needle+add,1)

json_anchor='\\"tls_epoch_pre\\":"+String((long long)gTlsEpochPre.load())'
if json_anchor not in s: raise SystemExit('15I JSON anchor missing')
fields='''\\"tls15i_version\\":\\\""+String(TLS15I_VERSION)+"\\\",\\"tls15i_last_error\\":"+String(gTls15iLastError.load())+",\\"tls15i_x509_verify_failed\\":"+(gTls15iX509VerifyFailed.load()?"true":"false")+",\\"tls15i_ca_verification_enabled\\":"+(gTls15iCaVerificationEnabled.load()?"true":"false")+","+'''
if '\\"tls15i_version\\"' not in s: s=s.replace(json_anchor,fields+json_anchor,1)

required=['TLS15I_VERSION','gTls15iLastError.store','tls15i_x509_verify_failed','client.setCACert(ECOFLOW_CA_BUNDLE);']
for token in required:
    if token not in s: raise SystemExit('15I required token missing: '+token)
if executable_set_insecure(s): raise SystemExit('15I security regression after patch')
p.write_text(s,encoding='utf-8')
print('15I runtime X509 provenance applied; CA verification remains enabled')
