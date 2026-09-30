#!/usr/bin/env python3
from pathlib import Path

p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')

# 15J is diagnostic-only and fail-closed. Do not weaken certificate validation.
def executable_set_insecure(text):
    for line in text.splitlines():
        code=line.split('//',1)[0]
        if 'setInsecure(' in code and not code.lstrip().startswith(('#','"',"'")):
            return True
    return False

required=['TLS15I_VERSION="9.36.7.15I-X509-ROOTCAUSE"','client.setCACert(ECOFLOW_CA_BUNDLE);','DigiCert Global Root G2']
for token in required:
    if token not in s: raise SystemExit('15J prerequisite missing: '+token)
if executable_set_insecure(s): raise SystemExit('15J security regression before patch')

s=s.replace('TLS15I_VERSION="9.36.7.15I-X509-ROOTCAUSE"','TLS15I_VERSION="9.36.7.15J-X509-VERIFY-DIAG"',1)

# Record the exact bundled trust anchor identity and size in runtime JSON. This
# distinguishes a malformed/truncated embedded PEM from peer-chain failures.
anchor='static const char* TLS15I_VERSION="9.36.7.15J-X509-VERIFY-DIAG";'
extra='''\nstatic const char* TLS15J_TRUST_ANCHOR="DigiCert Global Root G2";\nstatic std::atomic<uint32_t> gTls15jCaPemBytes{0};\n'''
if 'TLS15J_TRUST_ANCHOR' not in s:
    s=s.replace(anchor,anchor+extra,1)

ca_call='client.setCACert(ECOFLOW_CA_BUNDLE);'
if 'gTls15jCaPemBytes.store' not in s:
    s=s.replace(ca_call,'gTls15jCaPemBytes.store((uint32_t)strlen(ECOFLOW_CA_BUNDLE),std::memory_order_relaxed);\n  '+ca_call,1)

json_anchor='\\"tls15i_version\\":\\\""+String(TLS15I_VERSION)+"\\\",'
fields='\\"tls15j_trust_anchor\\":\\\""+String(TLS15J_TRUST_ANCHOR)+"\\\",\\"tls15j_ca_pem_bytes\\":"+String(gTls15jCaPemBytes.load())+",'
if '\\"tls15j_trust_anchor\\"' not in s:
    if json_anchor not in s: raise SystemExit('15J JSON anchor missing')
    s=s.replace(json_anchor,json_anchor+fields,1)

# Preserve the raw mbedTLS error already captured by 15I.  -0x2700/-9984 is a
# composite X509 verify failure; WiFiClientSecure does not expose peer verify
# flags through its public API in this Arduino core, so do not invent flags.
marker='''\n// 15J diagnostic contract: raw lastError + trust-anchor provenance.\n// Exact peer verify flags require lower-level mbedTLS instrumentation; do not infer them.\n'''
if '15J diagnostic contract:' not in s: s += marker

if executable_set_insecure(s): raise SystemExit('15J security regression after patch')
p.write_text(s,encoding='utf-8')
print('15J X509 diagnostics applied; CA verification remains mandatory')
