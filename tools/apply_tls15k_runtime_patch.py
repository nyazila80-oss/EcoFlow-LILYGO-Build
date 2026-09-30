#!/usr/bin/env python3
from pathlib import Path
p=Path('src/powerstream_api.cpp'); s=p.read_text(encoding='utf-8')
if 'gTls15jVerifyFlags' not in s: raise SystemExit('15K requires 15J runtime first')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s: raise SystemExit('15K CA invariant missing')
decl='''\nextern uint32_t tls15k_get_chain_flags(int depth);\nextern const char* tls15k_get_chain_subject(int depth);\nextern const char* tls15k_get_chain_issuer(int depth);\nextern const char* tls15k_get_chain_sha256(int depth);\n'''
if 'tls15k_get_chain_sha256' not in s:
    anchor='extern int tls15j_get_verify_depth(void);\n'
    if anchor not in s: raise SystemExit('15K declaration anchor missing')
    s=s.replace(anchor,anchor+decl,1)
helper=r'''
static String tls15kJsonEscape(const char* p){
  String o; if(!p) return o;
  for(size_t i=0;p[i] && i<191;i++){
    const char c=p[i];
    if(c=='\\' || c=='\"'){o+='\\';o+=c;}
    else if((unsigned char)c>=0x20)o+=c;
  }
  return o;
}
static String tls15kChainJson(){
  String o="[";
  for(int d=0;d<4;d++){
    const char* fp=tls15k_get_chain_sha256(d); if(!fp || !fp[0]) continue;
    if(o.length()>1)o+=",";
    o+="{\"depth\":"+String(d)+",\"flags_raw\":"+String(tls15k_get_chain_flags(d));
    o+=",\"subject\":\""+tls15kJsonEscape(tls15k_get_chain_subject(d))+"\"";
    o+=",\"issuer\":\""+tls15kJsonEscape(tls15k_get_chain_issuer(d))+"\"";
    o+=",\"sha256\":\""+String(fp)+"\"}";
  }
  o+="]"; return o;
}
'''
if 'tls15kChainJson' not in s:
    anchor='static String maskKey(const String& s) {'
    if anchor not in s: raise SystemExit('15K helper anchor missing')
    s=s.replace(anchor,helper+'\n'+anchor,1)
json_anchor='\\"tls15j_version\\":\\\""+String(TLS15J_VERSION)+"\\\",'
if json_anchor not in s: raise SystemExit('15K JSON anchor missing')
fields='\\"tls15k_version\\":\\\"9.36.7.15K-X509-CHAIN-PROBE\\\",\\"tls15k_chain\\":"+tls15kChainJson()+",'
if '\\"tls15k_version\\"' not in s: s=s.replace(json_anchor,fields+json_anchor,1)
for token in ('tls15k_chain','tls15k_get_chain_sha256','client.setCACert(ECOFLOW_CA_BUNDLE);'):
    if token not in s: raise SystemExit('15K token missing: '+token)
s=s.replace('9.36.7.15J-X509-VERIFY-FLAGS','9.36.7.15K-X509-CHAIN-PROBE')
p.write_text(s,encoding='utf-8')
cfg=Path('include/config.h'); c=cfg.read_text(encoding='utf-8')
c=c.replace('2.4.5.9.36.7.15J-X509-VERIFY-FLAGS','2.4.5.9.36.7.15K-X509-CHAIN-PROBE')
cfg.write_text(c,encoding='utf-8')
Path('data/fs_version.txt').write_text('2.4.5.9.36.7.15K-X509-CHAIN-PROBE\n',encoding='utf-8')
print('15K runtime chain telemetry applied; TLS verification remains fail-closed')
