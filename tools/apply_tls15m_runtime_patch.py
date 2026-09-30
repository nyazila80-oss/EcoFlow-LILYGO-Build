#!/usr/bin/env python3
from pathlib import Path
p=Path('src/powerstream_api.cpp'); s=p.read_text(encoding='utf-8')
for token in ('TLS15I_VERSION="9.36.7.15J-X509-VERIFY-DIAG"','TLS15J_TRUST_ANCHOR="DigiCert Global Root G2"','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if token not in s: raise SystemExit('15M prerequisite missing: '+token)
# Guard against accidentally importing the later experimental extra trust anchor.
if 'MIIDrzCCApegAwIBAgIQCDvgVpBCRrGhdWrJWZHHSj' in s:
    raise SystemExit('15M clean probe refuses 15K/15L extra trust anchor')

decl='''\nextern uint32_t tls15j_get_verify_flags(void);\nextern int tls15j_get_verify_depth(void);\nextern uint32_t tls15m_get_depth_flags(int depth);\nextern const char* tls15m_get_subject(int depth);\nextern const char* tls15m_get_issuer(int depth);\n'''
anchor='#include <atomic>\n'
if 'tls15m_get_depth_flags' not in s:
    if anchor not in s: raise SystemExit('15M include anchor missing')
    s=s.replace(anchor,anchor+decl,1)
helper='''\nstatic String tls15mJsonEscape(const char* in){\n  String o; if(!in) return o;\n  for(size_t i=0; in[i] && i<191; ++i){ char c=in[i];\n    if(c=='\\\\' || c=='\\"'){ o+='\\\\'; o+=c; } else if((unsigned char)c>=0x20) o+=c;\n  } return o;\n}\n'''
anchor='static const char* TLS15J_TRUST_ANCHOR="DigiCert Global Root G2";\n'
if 'tls15mJsonEscape' not in s:
    if anchor not in s: raise SystemExit('15M runtime anchor missing')
    s=s.replace(anchor,anchor+'static const char* TLS15M_VERSION="9.36.7.15M-CLEAN-CHAIN-PROBE";\n'+helper,1)
json_anchor='\\"tls15j_trust_anchor\\":\\\""+String(TLS15J_TRUST_ANCHOR)+"\\\",'
fields='''\\"tls15m_version\\":\\\""+String(TLS15M_VERSION)+"\\\",\\"tls15m_verify_flags_raw\\":"+String(tls15j_get_verify_flags())+",\\"tls15m_verify_depth\\":"+String(tls15j_get_verify_depth())+",\\"tls15m_chain\\":["+
 String("{\\\"depth\\\":0,\\\"flags\\\":")+String(tls15m_get_depth_flags(0))+",\\\"subject\\\":\\\""+tls15mJsonEscape(tls15m_get_subject(0))+"\\\",\\\"issuer\\\":\\\""+tls15mJsonEscape(tls15m_get_issuer(0))+"\\\"},"+
 String("{\\\"depth\\\":1,\\\"flags\\\":")+String(tls15m_get_depth_flags(1))+",\\\"subject\\\":\\\""+tls15mJsonEscape(tls15m_get_subject(1))+"\\\",\\\"issuer\\\":\\\""+tls15mJsonEscape(tls15m_get_issuer(1))+"\\\"},"+
 String("{\\\"depth\\\":2,\\\"flags\\\":")+String(tls15m_get_depth_flags(2))+",\\\"subject\\\":\\\""+tls15mJsonEscape(tls15m_get_subject(2))+"\\\",\\\"issuer\\\":\\\""+tls15mJsonEscape(tls15m_get_issuer(2))+"\\\"},"+
 String("{\\\"depth\\\":3,\\\"flags\\\":")+String(tls15m_get_depth_flags(3))+",\\\"subject\\\":\\\""+tls15mJsonEscape(tls15m_get_subject(3))+"\\\",\\\"issuer\\\":\\\""+tls15mJsonEscape(tls15m_get_issuer(3))+"\\\"}],'''
if '\\"tls15m_version\\"' not in s:
    if json_anchor not in s: raise SystemExit('15M JSON anchor missing')
    s=s.replace(json_anchor,json_anchor+fields,1)
p.write_text(s,encoding='utf-8')
print('15M runtime telemetry applied; original 15J trust store retained')
