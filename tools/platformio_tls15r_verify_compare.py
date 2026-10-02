#!/usr/bin/env python3
Import('env')
from pathlib import Path

pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15R: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('tls15p_get_direct_sig_rc','tls15q_get_pair_link','s_tls15p_seen','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15R requires 15P/15Q state: '+t)

decl='''
// 15R observation-only: compare verify_ext with plain pk_verify and expose key facts.
int tls15r_get_plain_rc(int depth);
int tls15r_get_issuer_pk_type(int depth);
int tls15r_get_issuer_pk_bits(int depth);
int tls15r_get_sig_opts_null(int depth);
int tls15r_get_hash_len(int depth);
'''
if 'tls15r_get_plain_rc' not in h: h += decl

storage=r'''
static volatile int s_tls15r_plain_rc[TLS15M_MAX_DEPTH]={-32768,-32768,-32768,-32768};
static volatile int s_tls15r_issuer_pk_type[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15r_issuer_pk_bits[TLS15M_MAX_DEPTH]={0,0,0,0};
static volatile int s_tls15r_sig_opts_null[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15r_hash_len[TLS15M_MAX_DEPTH]={0,0,0,0};
int tls15r_get_plain_rc(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15r_plain_rc[d]:-32768;}
int tls15r_get_issuer_pk_type(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15r_issuer_pk_type[d]:-1;}
int tls15r_get_issuer_pk_bits(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15r_issuer_pk_bits[d]:0;}
int tls15r_get_sig_opts_null(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15r_sig_opts_null[d]:-1;}
int tls15r_get_hash_len(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15r_hash_len[d]:0;}
static int tls15r_plain_verify(const mbedtls_x509_crt *child,mbedtls_x509_crt *issuer){
 if(!child||!issuer||!child->tbs.p||!child->tbs.len||!child->sig.p||!child->sig.len)return -32767;
 const mbedtls_md_info_t *md=mbedtls_md_info_from_type(child->sig_md); if(!md)return -32766;
 unsigned char hash[64]={0}; size_t hlen=mbedtls_md_get_size(md); if(!hlen||hlen>sizeof(hash))return -32765;
 int rc=mbedtls_md(md,child->tbs.p,child->tbs.len,hash); if(rc!=0)return rc;
 return mbedtls_pk_verify(&issuer->pk,child->sig_md,hash,hlen,child->sig.p,child->sig.len);
}
static void tls15r_probe_pair(int d){
 if(d<0||d>=TLS15M_MAX_DEPTH-1||!s_tls15p_seen[d]||!s_tls15p_seen[d+1])return;
 const mbedtls_x509_crt *child=s_tls15p_seen[d]; mbedtls_x509_crt *issuer=s_tls15p_seen[d+1];
 s_tls15r_plain_rc[d]=tls15r_plain_verify(child,issuer);
 s_tls15r_issuer_pk_type[d]=(int)mbedtls_pk_get_type(&issuer->pk);
 s_tls15r_issuer_pk_bits[d]=(int)mbedtls_pk_get_bitlen(&issuer->pk);
 s_tls15r_sig_opts_null[d]=(child->sig_opts==nullptr)?1:0;
 const mbedtls_md_info_t *md=mbedtls_md_info_from_type(child->sig_md);
 s_tls15r_hash_len[d]=md?(int)mbedtls_md_get_size(md):0;
}
'''
a='static char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\n'
if 's_tls15r_plain_rc' not in s:
    if a not in s: raise RuntimeError('15R storage anchor missing')
    s=s.replace(a,storage+a,1)

# Run only after 15P has both adjacent certs and has performed its ext verification.
old='                s_tls15p_direct_sig_rc[depth-1]=tls15p_verify_cert_sig(s_tls15p_seen[depth-1],crt);'
new=old+'\n                tls15r_probe_pair(depth-1);'
if new not in s:
    if old not in s: raise RuntimeError('15R first pair anchor missing')
    s=s.replace(old,new,1)
old2='                s_tls15p_direct_sig_rc[depth]=tls15p_verify_cert_sig(crt,s_tls15p_seen[depth+1]);'
new2=old2+'\n                tls15r_probe_pair(depth);'
if new2 not in s:
    if old2 not in s: raise RuntimeError('15R second pair anchor missing')
    s=s.replace(old2,new2,1)

oldr='s_tls15q_seen[i]=0; s_tls15q_sig_md[i]=-1; s_tls15q_sig_pk[i]=-1; s_tls15q_tbs_len[i]=0; s_tls15q_sig_len[i]=0; s_tls15q_pair_link[i]=-1;'
newr=oldr+' s_tls15r_plain_rc[i]=-32768; s_tls15r_issuer_pk_type[i]=-1; s_tls15r_issuer_pk_bits[i]=0; s_tls15r_sig_opts_null[i]=-1; s_tls15r_hash_len[i]=0;'
if newr not in s:
    if oldr not in s: raise RuntimeError('15R reset anchor missing')
    s=s.replace(oldr,newr,1)

if 'MBEDTLS_SSL_VERIFY_REQUIRED' not in s: raise RuntimeError('15R safety invariant lost')
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')

proj=Path(env['PROJECT_DIR'])/'src'/'powerstream_api.cpp'; p=proj.read_text(encoding='utf-8')
inc='#include <WiFiClientSecure.h>'
extern='''extern int tls15r_get_plain_rc(int depth);
extern int tls15r_get_issuer_pk_type(int depth);
extern int tls15r_get_issuer_pk_bits(int depth);
extern int tls15r_get_sig_opts_null(int depth);
extern int tls15r_get_hash_len(int depth);'''
if extern not in p:
    if inc not in p: raise RuntimeError('15R project include anchor missing')
    p=p.replace(inc,inc+'\n'+extern,1)
field='\\"heavy_owner\\":\\"'
if 'tls15r_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15R stable JSON anchor missing')
    def arr(fn): return '"+String('+fn+'(0))+","+String('+fn+'(1))+","+String('+fn+'(2))+","+String('+fn+'(3))+"'
    insert='\\"tls15r_version\\":\\"9.36.7.15R-VERIFY-COMPARE\\",'
    insert+='\\"tls15r_plain_rc\\":['+arr('tls15r_get_plain_rc')+'],'
    insert+='\\"tls15r_issuer_pk_type\\":['+arr('tls15r_get_issuer_pk_type')+'],'
    insert+='\\"tls15r_issuer_pk_bits\\":['+arr('tls15r_get_issuer_pk_bits')+'],'
    insert+='\\"tls15r_sig_opts_null\\":['+arr('tls15r_get_sig_opts_null')+'],'
    insert+='\\"tls15r_hash_len\\":['+arr('tls15r_get_hash_len')+'],'
    p=p[:pos]+insert+p[pos:]
for key in ('tls15r_version','tls15r_plain_rc','tls15r_issuer_pk_type','tls15r_issuer_pk_bits','tls15r_sig_opts_null','tls15r_hash_len'):
    if p.count(key)!=1: raise RuntimeError('15R JSON invariant failed: '+key)
proj.write_text(p,encoding='utf-8')
print('15R verify comparison installed; observation-only; VERIFY_REQUIRED preserved')
