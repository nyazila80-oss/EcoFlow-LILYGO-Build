#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# Diagnostic-only RAM attribution. No TLS threshold, CA, JK/NimBLE host or WebUI
# behaviour is changed. Measure INTERNAL|8BIT fragmentation around the existing
# idle PowerStream-client reclaim and two scheduler settling points.
decl='''
static std::atomic<uint32_t> g15aiPreFree{0},g15aiPreLargest{0},g15aiPreBlocks{0};
static std::atomic<uint32_t> g15aiPostFree{0},g15aiPostLargest{0},g15aiPostBlocks{0};
static std::atomic<uint32_t> g15aiTickFree{0},g15aiTickLargest{0},g15aiTickBlocks{0};
static std::atomic<uint32_t> g15aiSettleFree{0},g15aiSettleLargest{0},g15aiSettleBlocks{0};
static inline void tls15aiSnap(std::atomic<uint32_t>& fr,std::atomic<uint32_t>& lg,std::atomic<uint32_t>& blocks){
  multi_heap_info_t i{}; heap_caps_get_info(&i,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  fr.store((uint32_t)i.total_free_bytes,std::memory_order_relaxed);
  lg.store((uint32_t)i.largest_free_block,std::memory_order_relaxed);
  blocks.store((uint32_t)i.free_blocks,std::memory_order_relaxed);
}
'''
anchor='static std::atomic<uint32_t> gFragPsramTotal{0},gFragPsramFree{0},gFragPsramLargest{0};'
if 'g15aiPreFree' not in s:
    if s.count(anchor)!=1: raise RuntimeError('15AI declaration anchor missing/non-unique')
    s=s.replace(anchor,anchor+decl,1)

old='''  bool psBleReleased=false;
  if(!powerStreamBleLabReclaimIdleClientForCloud(psBleReleased)){
    err="Cloud TLS blockiert: PowerStream BLE aktiv/busy";
    return false;
  }
  if(psBleReleased) vTaskDelay(pdMS_TO_TICKS(1));
  if(!heap_caps_check_integrity_all(false)){'''
new='''  tls15aiSnap(g15aiPreFree,g15aiPreLargest,g15aiPreBlocks);
  bool psBleReleased=false;
  if(!powerStreamBleLabReclaimIdleClientForCloud(psBleReleased)){
    err="Cloud TLS blockiert: PowerStream BLE aktiv/busy";
    return false;
  }
  tls15aiSnap(g15aiPostFree,g15aiPostLargest,g15aiPostBlocks);
  if(psBleReleased) vTaskDelay(pdMS_TO_TICKS(1));
  tls15aiSnap(g15aiTickFree,g15aiTickLargest,g15aiTickBlocks);
  // Diagnostic settle only: test whether deferred scheduler/NimBLE cleanup changes
  // fragmentation. This is deliberately not claimed as a production fix.
  if(psBleReleased) vTaskDelay(pdMS_TO_TICKS(25));
  tls15aiSnap(g15aiSettleFree,g15aiSettleLargest,g15aiSettleBlocks);
  if(!heap_caps_check_integrity_all(false)){'''
if 'tls15aiSnap(g15aiPreFree' not in s:
    if s.count(old)!=1: raise RuntimeError('15AI reclaim attribution anchor missing/non-unique')
    s=s.replace(old,new,1)

# Reset per job so an aborted/busy job cannot inherit attribution values.
reset_anchor='''  gTlsDiagJobId.store(jobId,std::memory_order_relaxed);
  gTlsAttemptedThisJob.store(false,std::memory_order_relaxed);'''
reset_new=reset_anchor+'''\n  g15aiPreFree=0; g15aiPreLargest=0; g15aiPreBlocks=0;
  g15aiPostFree=0; g15aiPostLargest=0; g15aiPostBlocks=0;
  g15aiTickFree=0; g15aiTickLargest=0; g15aiTickBlocks=0;
  g15aiSettleFree=0; g15aiSettleLargest=0; g15aiSettleBlocks=0;'''
if 'g15aiPreFree=0' not in s:
    if s.count(reset_anchor)!=1: raise RuntimeError('15AI reset anchor missing/non-unique')
    s=s.replace(reset_anchor,reset_new,1)

# Export compact per-stage values in the existing status JSON.
json_anchor=''',\\"pending\\":"+(pending?"true":"false")+'''
json_new=''',\\"15ai_pre_free\\":"+String(g15aiPreFree.load())+",\\"15ai_pre_largest\\":"+String(g15aiPreLargest.load())+",\\"15ai_pre_blocks\\":"+String(g15aiPreBlocks.load())+",\\"15ai_post_free\\":"+String(g15aiPostFree.load())+",\\"15ai_post_largest\\":"+String(g15aiPostLargest.load())+",\\"15ai_post_blocks\\":"+String(g15aiPostBlocks.load())+",\\"15ai_tick_free\\":"+String(g15aiTickFree.load())+",\\"15ai_tick_largest\\":"+String(g15aiTickLargest.load())+",\\"15ai_tick_blocks\\":"+String(g15aiTickBlocks.load())+",\\"15ai_settle_free\\":"+String(g15aiSettleFree.load())+",\\"15ai_settle_largest\\":"+String(g15aiSettleLargest.load())+",\\"15ai_settle_blocks\\":"+String(g15aiSettleBlocks.load())+",\\"pending\\":"+(pending?"true":"false")+'''
if '15ai_pre_largest' not in s:
    if s.count(json_anchor)!=1: raise RuntimeError('15AI JSON anchor missing/non-unique')
    s=s.replace(json_anchor,json_new,1)

# Invariants: this diagnostic must not weaken security or touch shared JK/NimBLE.
if 'TLS_GET_MIN_LARGEST8 = 32768' not in s: raise RuntimeError('15AI TLS threshold changed/missing')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s: raise RuntimeError('15AI CA verification missing')
# Security scan must inspect executable source, not comments. Keep string literals
# visible so an actual setInsecure call is still rejected; only C/C++ comments are removed.
code=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
if re.search(r'\bsetInsecure\s*\(',code): raise RuntimeError('15AI insecure TLS forbidden')
if 'MBEDTLS_SSL_VERIFY_NONE' in code: raise RuntimeError('15AI TLS verify-none forbidden')
if s.count('tls15aiSnap(g15aiPreFree')!=1: raise RuntimeError('15AI attribution duplicated')

p.write_text(s,encoding='utf-8')
print('[15AI-DIAG] RAM attribution around PS BLE reclaim installed; security/runtime gates retained')
