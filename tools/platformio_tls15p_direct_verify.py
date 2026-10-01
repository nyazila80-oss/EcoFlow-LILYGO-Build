#!/usr/bin/env python3
Import('env')
from pathlib import Path

# 15P has two deliberately independent responsibilities:
#   1. patch the resolved Arduino WiFiClientSecure framework for direct
#      certificate-signature proof;
#   2. expose the proof in the project's already-existing job JSON.
# The project-side telemetry MUST NOT depend on any 15O runtime-source patch.

pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15P: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')

# Framework pre-scripts execute in order (15J -> 15M -> 15N -> 15O -> 15P).
# These prerequisites therefore apply only to the resolved framework package.
for t in ('tls15o_get_serial','tls15j_verify_cb','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15P requires 15O framework state: '+t)

# Fail closed: prove that the rootCABuff/setCACert branch still requires peer
# verification.  15P must never introduce or accept an insecure fallback.
ca_branch='''} else if (rootCABuff != NULL) {'''
verify_required='mbedtls_ssl_conf_authmode(&ssl_client->ssl_conf, MBEDTLS_SSL_VERIFY_REQUIRED);'
if ca_branch not in s or verify_required not in s:
    raise RuntimeError('15P: expected verified rootCABuff branch missing')
ca_pos=s.index(ca_branch); req_pos=s.index(verify_required,ca_pos); next_branch=s.find('} else if (',ca_pos+len(ca_branch))
if next_branch < 0 or not (ca_pos < req_pos < next_branch):
    raise RuntimeError('15P: VERIFY_REQUIRED is not scoped to rootCABuff/setCACert branch')

decl='''\n// 15P observation/proof: direct certificate-signature verification result.\nint tls15p_get_direct_sig_rc(int depth);\n'''
if 'tls15p_get_direct_sig_rc' not in h: h += decl

storage=r'''
static volatile int s_tls15p_direct_sig_rc[TLS15M_MAX_DEPTH]={-32768,-32768,-32768,-32768};
static mbedtls_x509_crt *s_tls15p_seen[TLS15M_MAX_DEPTH]={nullptr,nullptr,nullptr,nullptr};
int tls15p_get_direct_sig_rc(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15p_direct_sig_rc[d]:-32768;}
static int tls15p_verify_cert_sig(const mbedtls_x509_crt *child,mbedtls_x509_crt *issuer){
 if(!child||!issuer||!child->tbs.p||!child->tbs.len||!child->sig.p||!child->sig.len)return -32767;
 unsigned char hash[64]={0}; const mbedtls_md_info_t *md=mbedtls_md_info_from_type(child->sig_md);
 if(!md)return -32766; const size_t hlen=mbedtls_md_get_size(md); if(!hlen||hlen>sizeof(hash))return -32765;
 int rc=mbedtls_md(md,child->tbs.p,child->tbs.len,hash); if(rc!=0)return rc;
 return mbedtls_pk_verify_ext(child->sig_pk,&child->sig_opts,&issuer->pk,child->sig_md,hash,hlen,child->sig.p,child->sig.len);
}
'''
a='static char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\n'
if 's_tls15p_direct_sig_rc' not in s:
    if a not in s: raise RuntimeError('15P storage anchor missing')
    s=s.replace(a,storage+a,1)

old='            s_tls15o_pk_raw_len[depth]=crt->pk_raw.len;'
new=old+r'''
            s_tls15p_seen[depth]=crt;
            // mbedTLS verify callbacks are not required to arrive leaf-first.
            // Evaluate either adjacent pair as soon as both members have been seen.
            if(depth>0 && s_tls15p_seen[depth-1])
                s_tls15p_direct_sig_rc[depth-1]=tls15p_verify_cert_sig(s_tls15p_seen[depth-1],crt);
            if(depth+1<TLS15M_MAX_DEPTH && s_tls15p_seen[depth+1])
                s_tls15p_direct_sig_rc[depth]=tls15p_verify_cert_sig(crt,s_tls15p_seen[depth+1]);'''
if new not in s:
    if old not in s: raise RuntimeError('15P callback anchor missing')
    s=s.replace(old,new,1)

oldr="s_tls15n_verify_info[i][0]='\\0'; s_tls15n_raw_len[i]=0;"
newr=oldr+" s_tls15p_direct_sig_rc[i]=-32768; s_tls15p_seen[i]=nullptr;"
if newr not in s:
    if oldr not in s: raise RuntimeError('15P reset anchor missing')
    s=s.replace(oldr,newr,1)

for required in ('MBEDTLS_SSL_VERIFY_REQUIRED','mbedtls_pk_verify_ext','tls15p_direct_sig_rc'):
    if required not in h+s: raise RuntimeError('15P invariant missing: '+required)
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')

# Project telemetry: anchor only on a stable field that exists in the checked-in
# powerstream job JSON.  This intentionally has ZERO dependency on 15O project
# source telemetry or TLS15O_VERSION.  It therefore works during clean/buildfs
# as well as normal firmware builds, regardless of whether runtime diagnostic
# patches I..O have been applied to src/powerstream_api.cpp.
proj=Path(env['PROJECT_DIR'])/'src'/'powerstream_api.cpp'
p=proj.read_text(encoding='utf-8')
include='#include <WiFiClientSecure.h>'
extern='extern int tls15p_get_direct_sig_rc(int depth);'
if include not in p: raise RuntimeError('15P project include anchor missing')
if extern not in p:
    p=p.replace(include,include+'\n'+extern,1)

field='\\"heavy_owner\\":\\"'
if 'tls15p_version' not in p:
    pos=p.find(field)
    if pos < 0: raise RuntimeError('15P stable job JSON anchor missing: heavy_owner')
    # Insert inside the same return-expression String literal immediately before
    # heavy_owner.  No 15O-generated token is referenced here.
    insert='\\"tls15p_version\\":\\"9.36.7.15P-DIRECT-SIG-PROOF\\",\\"tls15p_direct_sig_rc\\":["+String(tls15p_get_direct_sig_rc(0))+","+String(tls15p_get_direct_sig_rc(1))+","+String(tls15p_get_direct_sig_rc(2))+","+String(tls15p_get_direct_sig_rc(3))+"],'
    p=p[:pos]+insert+p[pos:]

# Strong idempotence/invariant checks.  Count the JSON key, not the extern
# function name, because four getter calls are intentionally present.
if p.count('tls15p_version') != 1:
    raise RuntimeError('15P JSON telemetry invariant failed: version field count')
if p.count('\\"tls15p_direct_sig_rc\\"') != 1:
    raise RuntimeError('15P JSON telemetry invariant failed: result field count')
if p.count(extern) != 1:
    raise RuntimeError('15P project declaration invariant failed')
if field not in p:
    raise RuntimeError('15P damaged stable job JSON tail')
proj.write_text(p,encoding='utf-8')
print('15P direct signature proof installed; callback-order independent; project telemetry decoupled from 15O; setCACert/rootCABuff remains VERIFY_REQUIRED')
