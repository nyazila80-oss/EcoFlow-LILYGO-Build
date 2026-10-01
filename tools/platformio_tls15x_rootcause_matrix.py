#!/usr/bin/env python3
Import('env')
from pathlib import Path

pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15X: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('tls15p_get_direct_sig_rc','tls15q_get_pair_link','tls15r_get_plain_rc','s_tls15p_seen','MBEDTLS_SSL_VERIFY_REQUIRED'):
    if t not in h+s: raise RuntimeError('15X requires P/Q/R state: '+t)

decl='''
// 15X consolidated root-cause matrix. Observation-only.
int tls15x_get_hash_repeat_match(int depth);
int tls15x_get_sig_len_matches_key(int depth);
int tls15x_get_tbs_stable(int depth);
int tls15x_get_sig_stable(int depth);
int tls15x_get_pk_stable(int depth);
int tls15x_get_pair_class(int depth);
'''
if 'tls15x_get_pair_class' not in h: h += decl

storage=r'''
static volatile int s_tls15x_hash_repeat_match[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15x_sig_len_matches_key[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15x_tbs_stable[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15x_sig_stable[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15x_pk_stable[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15x_pair_class[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static uint32_t s_tls15x_tbs_fp[TLS15M_MAX_DEPTH]={0,0,0,0};
static uint32_t s_tls15x_sig_fp[TLS15M_MAX_DEPTH]={0,0,0,0};
static uint32_t s_tls15x_pk_fp[TLS15M_MAX_DEPTH]={0,0,0,0};
int tls15x_get_hash_repeat_match(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15x_hash_repeat_match[d]:-1;}
int tls15x_get_sig_len_matches_key(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15x_sig_len_matches_key[d]:-1;}
int tls15x_get_tbs_stable(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15x_tbs_stable[d]:-1;}
int tls15x_get_sig_stable(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15x_sig_stable[d]:-1;}
int tls15x_get_pk_stable(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15x_pk_stable[d]:-1;}
int tls15x_get_pair_class(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15x_pair_class[d]:-1;}
static uint32_t tls15x_fp(const unsigned char *p,size_t n){uint32_t h=2166136261u;if(!p)return 0;for(size_t i=0;i<n;i++){h^=p[i];h*=16777619u;}return h;}
static void tls15x_capture_cert(int d,const mbedtls_x509_crt *c){
 if(d<0||d>=TLS15M_MAX_DEPTH||!c)return;
 uint32_t tf=tls15x_fp(c->tbs.p,c->tbs.len), sf=tls15x_fp(c->sig.p,c->sig.len), pf=tls15x_fp(c->pk_raw.p,c->pk_raw.len);
 if(s_tls15x_tbs_fp[d]==0){s_tls15x_tbs_fp[d]=tf;s_tls15x_sig_fp[d]=sf;s_tls15x_pk_fp[d]=pf;s_tls15x_tbs_stable[d]=1;s_tls15x_sig_stable[d]=1;s_tls15x_pk_stable[d]=1;}
 else {if(s_tls15x_tbs_fp[d]!=tf)s_tls15x_tbs_stable[d]=0;if(s_tls15x_sig_fp[d]!=sf)s_tls15x_sig_stable[d]=0;if(s_tls15x_pk_fp[d]!=pf)s_tls15x_pk_stable[d]=0;}
}
static void tls15x_probe_pair(int d){
 if(d<0||d>=TLS15M_MAX_DEPTH-1||!s_tls15p_seen[d]||!s_tls15p_seen[d+1])return;
 const mbedtls_x509_crt *c=s_tls15p_seen[d]; mbedtls_x509_crt *iss=s_tls15p_seen[d+1];
 const mbedtls_md_info_t *md=mbedtls_md_info_from_type(c->sig_md);
 if(md){unsigned char a[64]={0},b[64]={0};size_t n=mbedtls_md_get_size(md);if(n&&n<=64&&mbedtls_md(md,c->tbs.p,c->tbs.len,a)==0&&mbedtls_md(md,c->tbs.p,c->tbs.len,b)==0)s_tls15x_hash_repeat_match[d]=(memcmp(a,b,n)==0)?1:0;}
 size_t bits=mbedtls_pk_get_bitlen(&iss->pk); if(bits)s_tls15x_sig_len_matches_key[d]=(c->sig.len==((bits+7)/8))?1:0;
 int link=tls15q_get_pair_link(d), ext=tls15p_get_direct_sig_rc(d), plain=tls15r_get_plain_rc(d);
 // class: 0=PASS, 1=identity mismatch, 2=both crypto paths fail, 3=ext-only fail, 4=plain-only fail, 5=inconclusive
 if(link==0)s_tls15x_pair_class[d]=1; else if(link==1&&ext==0&&plain==0)s_tls15x_pair_class[d]=0; else if(link==1&&ext!=0&&ext!=-32768&&plain!=0&&plain!=-32768)s_tls15x_pair_class[d]=2; else if(link==1&&ext!=0&&ext!=-32768&&plain==0)s_tls15x_pair_class[d]=3; else if(link==1&&ext==0&&plain!=0&&plain!=-32768)s_tls15x_pair_class[d]=4; else s_tls15x_pair_class[d]=5;
}
'''
a='static char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\n'
if 's_tls15x_hash_repeat_match' not in s:
    if a not in s: raise RuntimeError('15X storage anchor missing')
    s=s.replace(a,storage+a,1)
old='            s_tls15p_seen[depth]=crt;'
new='            tls15x_capture_cert(depth,crt);\n'+old
if new not in s:
    if old not in s: raise RuntimeError('15X capture anchor missing')
    s=s.replace(old,new,1)
old='                tls15r_probe_pair(depth-1);'
new=old+'\n                tls15x_probe_pair(depth-1);'
if new not in s:
    if old not in s: raise RuntimeError('15X pair1 anchor missing')
    s=s.replace(old,new,1)
old='                tls15r_probe_pair(depth);'
new=old+'\n                tls15x_probe_pair(depth);'
if new not in s:
    if old not in s: raise RuntimeError('15X pair2 anchor missing')
    s=s.replace(old,new,1)
oldr='s_tls15r_plain_rc[i]=-32768; s_tls15r_issuer_pk_type[i]=-1; s_tls15r_issuer_pk_bits[i]=0; s_tls15r_sig_opts_null[i]=-1; s_tls15r_hash_len[i]=0;'
newr=oldr+' s_tls15x_hash_repeat_match[i]=-1; s_tls15x_sig_len_matches_key[i]=-1; s_tls15x_tbs_stable[i]=-1; s_tls15x_sig_stable[i]=-1; s_tls15x_pk_stable[i]=-1; s_tls15x_pair_class[i]=-1; s_tls15x_tbs_fp[i]=0; s_tls15x_sig_fp[i]=0; s_tls15x_pk_fp[i]=0;'
if newr not in s:
    if oldr not in s: raise RuntimeError('15X reset anchor missing')
    s=s.replace(oldr,newr,1)
if 'MBEDTLS_SSL_VERIFY_REQUIRED' not in s: raise RuntimeError('15X safety invariant lost')
hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')

proj=Path(env['PROJECT_DIR'])/'src'/'powerstream_api.cpp'; p=proj.read_text(encoding='utf-8'); inc='#include <WiFiClientSecure.h>'
extern='''extern int tls15x_get_hash_repeat_match(int depth);
extern int tls15x_get_sig_len_matches_key(int depth);
extern int tls15x_get_tbs_stable(int depth);
extern int tls15x_get_sig_stable(int depth);
extern int tls15x_get_pk_stable(int depth);
extern int tls15x_get_pair_class(int depth);'''
if extern not in p:
    if inc not in p: raise RuntimeError('15X include anchor missing')
    p=p.replace(inc,inc+'\n'+extern,1)
field='\\"heavy_owner\\":\\"'
if 'tls15x_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15X JSON anchor missing')
    def arr(fn): return '"+String('+fn+'(0))+","+String('+fn+'(1))+","+String('+fn+'(2))+","+String('+fn+'(3))+"'
    insert='\\"tls15x_version\\":\\"9.36.7.15X-ROOTCAUSE-MATRIX\\",'
    for key,fn in [('hash_repeat_match','tls15x_get_hash_repeat_match'),('sig_len_matches_key','tls15x_get_sig_len_matches_key'),('tbs_stable','tls15x_get_tbs_stable'),('sig_stable','tls15x_get_sig_stable'),('pk_stable','tls15x_get_pk_stable'),('pair_class','tls15x_get_pair_class')]: insert+='\\"tls15x_'+key+'\\":['+arr(fn)+'],'
    p=p[:pos]+insert+p[pos:]
for key in ('tls15x_version','tls15x_hash_repeat_match','tls15x_sig_len_matches_key','tls15x_tbs_stable','tls15x_sig_stable','tls15x_pk_stable','tls15x_pair_class'):
    if p.count(key)!=1: raise RuntimeError('15X JSON invariant failed: '+key)
proj.write_text(p,encoding='utf-8')
print('15X consolidated root-cause matrix installed; observation-only; VERIFY_REQUIRED preserved')
