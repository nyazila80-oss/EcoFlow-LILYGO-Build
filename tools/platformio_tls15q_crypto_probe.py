#!/usr/bin/env python3
Import('env')
from pathlib import Path

pkg=env.PioPlatform().get_package_dir('framework-arduinoespressif32')
if not pkg: raise RuntimeError('15Q: framework unresolved')
base=Path(pkg)/'libraries'/'WiFiClientSecure'/'src'; hdr=base/'ssl_client.h'; cpp=base/'ssl_client.cpp'
h=hdr.read_text(encoding='utf-8'); s=cpp.read_text(encoding='utf-8')
for t in ('tls15p_get_direct_sig_rc','s_tls15o_ski','s_tls15o_aki','s_tls15o_pk_raw_len'):
    if t not in h+s: raise RuntimeError('15Q requires 15P/15O framework state: '+t)
if 'MBEDTLS_SSL_VERIFY_REQUIRED' not in s: raise RuntimeError('15Q: VERIFY_REQUIRED missing')

decl='''
// 15Q observation-only crypto/pair probe.
int tls15q_get_seen(int depth);
int tls15q_get_sig_md(int depth);
int tls15q_get_sig_pk(int depth);
int tls15q_get_tbs_len(int depth);
int tls15q_get_sig_len(int depth);
int tls15q_get_pair_link(int depth);
'''
if 'tls15q_get_pair_link' not in h: h += decl

storage=r'''
static volatile int s_tls15q_seen[TLS15M_MAX_DEPTH]={0,0,0,0};
static volatile int s_tls15q_sig_md[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15q_sig_pk[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
static volatile int s_tls15q_tbs_len[TLS15M_MAX_DEPTH]={0,0,0,0};
static volatile int s_tls15q_sig_len[TLS15M_MAX_DEPTH]={0,0,0,0};
static volatile int s_tls15q_pair_link[TLS15M_MAX_DEPTH]={-1,-1,-1,-1};
int tls15q_get_seen(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15q_seen[d]:0;}
int tls15q_get_sig_md(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15q_sig_md[d]:-1;}
int tls15q_get_sig_pk(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15q_sig_pk[d]:-1;}
int tls15q_get_tbs_len(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15q_tbs_len[d]:0;}
int tls15q_get_sig_len(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15q_sig_len[d]:0;}
int tls15q_get_pair_link(int d){return(d>=0&&d<TLS15M_MAX_DEPTH)?s_tls15q_pair_link[d]:-1;}
static int tls15q_hex_equal(const char *a,const char *b){return(a&&b&&a[0]&&b[0]&&strcmp(a,b)==0)?1:0;}
static void tls15q_recompute_links(){
 for(int d=0;d<TLS15M_MAX_DEPTH-1;++d){
  if(s_tls15p_seen[d]&&s_tls15p_seen[d+1])
   s_tls15q_pair_link[d]=tls15q_hex_equal(s_tls15o_aki[d],s_tls15o_ski[d+1]);
 }
}
'''
a='static char s_tls15n_verify_info[TLS15M_MAX_DEPTH][160] = {{0}};\n'
if 's_tls15q_seen' not in s:
    if a not in s: raise RuntimeError('15Q storage anchor missing')
    s=s.replace(a,storage+a,1)

old='            s_tls15p_seen[depth]=crt;'
new=old+r'''
            s_tls15q_seen[depth]=1;
            s_tls15q_sig_md[depth]=(int)crt->sig_md;
            s_tls15q_sig_pk[depth]=(int)crt->sig_pk;
            s_tls15q_tbs_len[depth]=(int)crt->tbs.len;
            s_tls15q_sig_len[depth]=(int)crt->sig.len;
            tls15q_recompute_links();'''
if new not in s:
    if old not in s: raise RuntimeError('15Q callback anchor missing')
    s=s.replace(old,new,1)

oldr="s_tls15p_direct_sig_rc[i]=-32768; s_tls15p_seen[i]=nullptr;"
newr=oldr+" s_tls15q_seen[i]=0; s_tls15q_sig_md[i]=-1; s_tls15q_sig_pk[i]=-1; s_tls15q_tbs_len[i]=0; s_tls15q_sig_len[i]=0; s_tls15q_pair_link[i]=-1;"
if newr not in s:
    if oldr not in s: raise RuntimeError('15Q reset anchor missing')
    s=s.replace(oldr,newr,1)

hdr.write_text(h,encoding='utf-8'); cpp.write_text(s,encoding='utf-8')

proj=Path(env['PROJECT_DIR'])/'src'/'powerstream_api.cpp'; p=proj.read_text(encoding='utf-8')
inc='#include <WiFiClientSecure.h>'
extern='''extern int tls15q_get_seen(int depth);
extern int tls15q_get_sig_md(int depth);
extern int tls15q_get_sig_pk(int depth);
extern int tls15q_get_tbs_len(int depth);
extern int tls15q_get_sig_len(int depth);
extern int tls15q_get_pair_link(int depth);'''
if extern not in p:
    if inc not in p: raise RuntimeError('15Q project include anchor missing')
    p=p.replace(inc,inc+'\n'+extern,1)
field='\\"heavy_owner\\":\\"'
if 'tls15q_version' not in p:
    pos=p.find(field)
    if pos<0: raise RuntimeError('15Q stable JSON anchor missing')
    def arr(fn): return '"+String('+fn+'(0))+","+String('+fn+'(1))+","+String('+fn+'(2))+","+String('+fn+'(3))+"'
    insert='\\"tls15q_version\\":\\"9.36.7.15Q-CRYPTO-PAIR-PROBE\\",'
    insert+='\\"tls15q_seen\\":['+arr('tls15q_get_seen')+'],'
    insert+='\\"tls15q_sig_md\\":['+arr('tls15q_get_sig_md')+'],'
    insert+='\\"tls15q_sig_pk\\":['+arr('tls15q_get_sig_pk')+'],'
    insert+='\\"tls15q_tbs_len\\":['+arr('tls15q_get_tbs_len')+'],'
    insert+='\\"tls15q_sig_len\\":['+arr('tls15q_get_sig_len')+'],'
    insert+='\\"tls15q_pair_link\\":['+arr('tls15q_get_pair_link')+'],'
    p=p[:pos]+insert+p[pos:]
for key in ('tls15q_version','tls15q_seen','tls15q_sig_md','tls15q_sig_pk','tls15q_tbs_len','tls15q_sig_len','tls15q_pair_link'):
    if p.count(key)!=1: raise RuntimeError('15Q JSON invariant failed: '+key)
proj.write_text(p,encoding='utf-8')
print('15Q crypto/pair probe installed; observation-only; VERIFY_REQUIRED preserved')
