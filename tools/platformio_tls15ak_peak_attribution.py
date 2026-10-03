#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# 15AK diagnostic only: classify the exact failed mbedTLS allocation during the
# verified client.connect() window. Do not weaken TLS or alter JK/NimBLE/WebUI
# ownership. 15AM intentionally changes only the admission threshold 32 -> 24KiB;
# downstream 15AM/15AN must therefore be verified, never rewritten backwards.
decl='''
static std::atomic<uint32_t> g15akFailSeq{0},g15akFirstSize{0},g15akFirstCaps{0};
static std::atomic<uint32_t> g15akFirstFree{0},g15akFirstLargest{0};
static std::atomic<uint32_t> g15akLastSize{0},g15akLastCaps{0};
static std::atomic<uint32_t> g15akLastFree{0},g15akLastLargest{0};
static std::atomic<uint32_t> g15akMinFree{0xFFFFFFFFu},g15akMinLargest{0xFFFFFFFFu};
static inline void tls15akAtomicMin(std::atomic<uint32_t>& a,uint32_t v){
  uint32_t p=a.load(std::memory_order_relaxed);
  while(v<p && !a.compare_exchange_weak(p,v,std::memory_order_relaxed)){}
}
'''
anchor='static std::atomic<bool> gTlsAllocWindow{false};'
if 'g15akFailSeq' not in s:
    if s.count(anchor)!=1: raise RuntimeError('15AK declaration anchor missing/non-unique')
    s=s.replace(anchor,anchor+decl,1)

hook_anchor='''  gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed);
  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(caps,std::memory_order_relaxed);'''
hook_new='''  const uint32_t seq=gTlsFailedAllocCount.fetch_add(1,std::memory_order_relaxed)+1U;
  gTlsFailedAllocSize.store((uint32_t)requestedSize,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(caps,std::memory_order_relaxed);
  const uint32_t f=(uint32_t)heap_caps_get_free_size(caps);
  const uint32_t l=(uint32_t)heap_caps_get_largest_free_block(caps);
  g15akFailSeq.store(seq,std::memory_order_relaxed);
  if(seq==1U){
    g15akFirstSize.store((uint32_t)requestedSize,std::memory_order_relaxed);
    g15akFirstCaps.store(caps,std::memory_order_relaxed);
    g15akFirstFree.store(f,std::memory_order_relaxed);
    g15akFirstLargest.store(l,std::memory_order_relaxed);
  }
  g15akLastSize.store((uint32_t)requestedSize,std::memory_order_relaxed);
  g15akLastCaps.store(caps,std::memory_order_relaxed);
  g15akLastFree.store(f,std::memory_order_relaxed);
  g15akLastLargest.store(l,std::memory_order_relaxed);
  tls15akAtomicMin(g15akMinFree,f); tls15akAtomicMin(g15akMinLargest,l);'''
if 'g15akFailSeq.store(seq' not in s:
    if s.count(hook_anchor)!=1: raise RuntimeError('15AK failed-allocation hook anchor missing/non-unique')
    s=s.replace(hook_anchor,hook_new,1)

reset_anchor='''  gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
  gTlsFailedAllocSize.store(0,std::memory_order_relaxed);'''
reset_new=reset_anchor+'''\n  g15akFailSeq=0; g15akFirstSize=0; g15akFirstCaps=0; g15akFirstFree=0; g15akFirstLargest=0;
  g15akLastSize=0; g15akLastCaps=0; g15akLastFree=0; g15akLastLargest=0;
  g15akMinFree=0xFFFFFFFFu; g15akMinLargest=0xFFFFFFFFu;'''
if 'g15akFirstSize=0' not in s:
    if s.count(reset_anchor)!=1: raise RuntimeError('15AK reset anchor missing/non-unique')
    s=s.replace(reset_anchor,reset_new,1)

json_anchor=''',\\"message\\":\\""+m+"\\"}";'''
json_new=''',\\"15ak_fail_seq\\":"+String(g15akFailSeq.load())+",\\"15ak_first_size\\":"+String(g15akFirstSize.load())+",\\"15ak_first_caps\\":"+String(g15akFirstCaps.load())+",\\"15ak_first_free\\":"+String(g15akFirstFree.load())+",\\"15ak_first_largest\\":"+String(g15akFirstLargest.load())+",\\"15ak_last_size\\":"+String(g15akLastSize.load())+",\\"15ak_last_caps\\":"+String(g15akLastCaps.load())+",\\"15ak_last_free\\":"+String(g15akLastFree.load())+",\\"15ak_last_largest\\":"+String(g15akLastLargest.load())+",\\"15ak_min_free\\":"+String(g15akMinFree.load()==0xFFFFFFFFu?0:g15akMinFree.load())+",\\"15ak_min_largest\\":"+String(g15akMinLargest.load()==0xFFFFFFFFu?0:g15akMinLargest.load())+",\\"message\\":\\""+m+"\\"}";'''
if '15ak_first_size' not in s:
    if s.count(json_anchor)!=1: raise RuntimeError('15AK JSON anchor missing/non-unique')
    s=s.replace(json_anchor,json_new,1)

# Determine the current lineage before enforcing the threshold invariant.
version_re=re.compile(r'tls15z_version\\\":\\\"([^\\\"]+)')
versions=version_re.findall(s)
if len(versions)!=1: raise RuntimeError('15AK provenance missing/non-unique: '+repr(versions))
version=versions[0]
thr32='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
thr24='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
if version in ('9.36.7.15AM-PREFLIGHT-AB-24K','9.36.7.15AN-TLS-INTERNAL8-FIX'):
    if s.count(thr24)!=1 or s.count(thr32)!=0:
        raise RuntimeError('15AK downstream threshold invariant failed: expected canonical 24KiB')
else:
    if s.count(thr32)!=1:
        raise RuntimeError('15AK TLS admission threshold changed/missing: expected canonical 32KiB')

# Hard safety/fixed-point gates.
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s: raise RuntimeError('15AK CA verification missing')
code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AK insecure TLS forbidden')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AK TLS verify-none forbidden')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AK connect cardinality changed')
for key in ('g15akFailSeq.store(seq','g15akFirstSize=0','15ak_first_size'):
    if key not in s: raise RuntimeError('15AK fixed-point telemetry missing: '+key)

p.write_text(s,encoding='utf-8')
print('[15AK-DIAG] fixed point PASS; lineage=%s; threshold=%s; exact allocation telemetry/security gates retained' % (version,'24KiB' if thr24 in s else '32KiB'))
